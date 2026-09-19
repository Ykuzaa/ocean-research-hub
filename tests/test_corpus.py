import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.corpus import domain_ids, load_seed
from ocean_research_hub.corpus.openalex import pdf_candidates, resolve, title_similarity
from ocean_research_hub.ingestion.models import MetadataPayload
from ocean_research_hub.ingestion.pdf import ParsedPage, ParsedPdf, PdfParser
from ocean_research_hub.ingestion.repository import SqlitePaperRepository

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def test_seed_papers_only_reference_known_domains_and_have_unique_titles() -> None:
    seed = load_seed()
    known = set(domain_ids())
    titles = [paper["title"].lower() for paper in seed["papers"]]
    assert len(titles) == len(set(titles))
    for paper in seed["papers"]:
        assert paper["domains"] and set(paper["domains"]) <= known


def test_seed_contains_no_emoji() -> None:
    text = Path("src/ocean_research_hub/corpus/seed.json").read_text(encoding="utf-8")
    assert not EMOJI.search(text)


def test_title_similarity_ignores_case_and_punctuation() -> None:
    assert title_similarity("GLONET: Mercator's End-to-End Neural", "glonet mercator s end to end neural") == 1.0
    assert title_similarity("XiHe ocean forecasting", "WenHai eddying ocean") < 0.9


def test_pdf_candidates_put_arxiv_first() -> None:
    work = {
        "best_oa_location": {"pdf_url": "https://publisher.example/paper.pdf"},
        "locations": [
            {"landing_page_url": "https://doi.org/10.1/x", "pdf_url": "https://publisher.example/paper.pdf"},
            {"landing_page_url": "https://arxiv.org/abs/2402.02995", "pdf_url": None},
        ],
    }
    assert pdf_candidates(work) == [
        "https://arxiv.org/pdf/2402.02995",
        "https://publisher.example/paper.pdf",
    ]


def test_resolve_keeps_the_journal_doi_and_pools_the_preprint_pdf() -> None:
    title = "XiHe: A Data-Driven Model for Global Ocean Eddy-Resolving Forecasting"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"id": "W-preprint", "doi": "https://doi.org/10.48550/arxiv.2402.02995", "title": title,
             "locations": [{"landing_page_url": "https://arxiv.org/abs/2402.02995"}]},
            {"id": "W-journal", "doi": "https://doi.org/10.1234/xihe", "title": title, "locations": []},
            {"id": "W-other", "doi": "https://doi.org/10.1234/other", "title": "Unrelated ocean paper"},
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resolution = resolve(client, title)

    assert resolution.openalex_id == "W-journal"
    assert resolution.doi == "10.1234/xihe"
    assert resolution.pdf_candidates == ["https://arxiv.org/pdf/2402.02995"]


def test_resolve_with_a_curated_doi_still_pools_the_preprint_pdf() -> None:
    title = "GLONET: Mercator's End-to-End Neural Global Ocean Forecasting System"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("doi:10.1029/2025jh000686"):
            return httpx.Response(200, json={
                "id": "W-journal", "doi": "https://doi.org/10.1029/2025jh000686", "title": title,
                "best_oa_location": {"pdf_url": "https://onlinelibrary.wiley.com/doi/pdfdirect/x"},
            })
        return httpx.Response(200, json={"results": [
            {"id": "W-preprint", "doi": "https://doi.org/10.48550/arxiv.2412.05454",
             "title": "GLONET: Mercator‐s end‐to‐end neural Global Ocean forecasting system",
             "locations": [{"landing_page_url": "http://arxiv.org/abs/2412.05454"}]},
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resolution = resolve(client, title, doi="10.1029/2025jh000686")

    assert resolution.doi == "10.1029/2025jh000686"
    assert resolution.pdf_candidates[0] == "https://arxiv.org/pdf/2412.05454"


def test_resolve_refuses_a_near_but_different_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"id": "W1", "title": "A completely different study of waves"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert not resolve(client, "Bias correction of significant wave height with LSTM neural networks").found


class _Metadata:
    async def fetch(self, doi: str) -> MetadataPayload:
        return MetadataPayload(title="GLONET", doi=doi)


def test_metadata_only_paper_is_upgraded_when_its_pdf_is_ingested_later(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    app = create_app(
        repository=SqlitePaperRepository(tmp_path / "papers.db"), pdf_parser=_StubParser(),
        metadata_provider=_Metadata(),
    )

    with TestClient(app) as client:
        meta_only = client.post("/api/papers/ingest", json={"doi": "10.1029/x", "domains": ["forecasting"]})
        upgraded = client.post(
            "/api/papers/ingest",
            json={"doi": "10.1029/x", "pdf_path": str(pdf), "domains": ["currents"]},
        )

    assert meta_only.json()["paper"]["workflow_status"] == "INGESTED"
    assert upgraded.status_code == 200
    paper = upgraded.json()["paper"]
    assert paper["id"] == meta_only.json()["paper"]["id"]
    assert paper["workflow_status"] == "EXTRACTED"
    assert paper["record"]["training"]["optimizer"]["value"] == "Adam"
    assert paper["domains"] == ["forecasting", "currents"]


class _MetadataWithPdf:
    async def fetch(self, doi: str) -> MetadataPayload:
        return MetadataPayload(title="A review", doi=doi, pdf_url="https://publisher.example/review.pdf")


class _ForbiddenParser(PdfParser):
    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        raise AssertionError("extract=False must never download or parse a PDF")


def test_extract_false_never_touches_a_pdf_even_when_metadata_links_one(tmp_path: Path) -> None:
    app = create_app(
        repository=SqlitePaperRepository(tmp_path / "papers.db"), pdf_parser=_ForbiddenParser(),
        metadata_provider=_MetadataWithPdf(),
    )

    with TestClient(app) as client:
        response = client.post("/api/papers/ingest", json={"doi": "10.1234/review", "extract": False})

    assert response.status_code == 201
    assert response.json()["paper"]["workflow_status"] == "INGESTED"
    assert response.json()["paper"]["record"]["paper"]["title"]["value"] == "A review"


class _StubParser(PdfParser):
    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        return ParsedPdf(pages=[ParsedPage(1, "We use the Adam optimizer.")], source_name=source_name)


def test_domains_are_stored_merged_filtered_and_counted(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    app = create_app(
        repository=SqlitePaperRepository(tmp_path / "papers.db"), pdf_parser=_StubParser(),
    )

    with TestClient(app) as client:
        first = client.post("/api/papers/ingest", json={"pdf_path": str(pdf), "domains": ["sst"]})
        again = client.post("/api/papers/ingest", json={"pdf_path": str(pdf), "domains": ["forecasting"]})
        in_sst = client.get("/api/papers", params={"domain": "sst"}).json()
        in_waves = client.get("/api/papers", params={"domain": "waves"}).json()
        domains = {d["id"]: d["paper_count"] for d in client.get("/api/domains").json()}
        unknown = client.post("/api/papers/ingest", json={"pdf_path": str(pdf), "domains": ["astrology"]})

    assert first.status_code == 201
    assert again.json()["paper"]["domains"] == ["sst", "forecasting"]
    assert in_sst["total"] == 1 and in_sst["papers"][0]["domains"] == ["sst", "forecasting"]
    assert in_waves["total"] == 0
    assert domains["sst"] == 1 and domains["forecasting"] == 1 and domains["waves"] == 0
    assert len(domains) == 19
    assert unknown.status_code == 422
