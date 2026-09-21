"""Reproducible real-PDF extraction, benchmark, and audit-report runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator
from dotenv import load_dotenv

from ocean_research_hub.evaluation.benchmark import benchmark, load_golden
from ocean_research_hub.evaluation.models import (
    GoldenPaper, PaperPrediction, PredictedField, PredictionSet,
)
from ocean_research_hub.ingestion.pdf import ParsedPdf, PdfParser, ScientificExtractor
from ocean_research_hub.ingestion.semantic import (
    AnthropicClient, GeminiClient, SemanticExtractionError, SemanticExtractor,
)
from ocean_research_hub.schemas.paper_record import EvidenceField, PaperRecord


AUDIT_PATHS = (
    "scientific_framing.problem", "scientific_framing.objective", "scientific_framing.task_type",
    "data.datasets", "data.inputs", "data.outputs", "data.variables", "data.spatial_resolution",
    "data.temporal_resolution", "data.splits.train", "data.splits.validation", "data.splits.test",
    "data.preprocessing.missing_data", "data.preprocessing.masking", "data.preprocessing.regridding",
    "data.preprocessing.interpolation", "data.preprocessing.normalization",
    "architecture.family", "architecture.summary", "architecture.encoder", "architecture.decoder",
    "architecture.blocks", "architecture.hidden_dimensions", "architecture.activations",
    "architecture.normalization_layers", "training.optimizer", "training.learning_rate",
    "training.scheduler", "training.batch_size", "training.epochs_or_steps", "training.hardware",
    "training.training_time", "objective.primary_loss", "objective.auxiliary_losses",
    "evaluation.baselines", "evaluation.metrics", "evaluation.evaluation_datasets",
    "evaluation.ablations", "results.headline", "limitations.author_reported",
    "limitations.future_work", "limitations.reproducibility",
)

OCEANNET_SUPPLEMENT_URL = "https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41598-024-72145-0/MediaObjects/41598_2024_72145_MOESM1_ESM.pdf"


class AuditDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    decision: Literal["PASS", "FAIL"]
    expected_value: Any = None
    extracted_value: Any = None
    evidence_location: str
    reason: str

    @field_validator("evidence_location", "reason")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("auditor decision text must not be blank")
        return value


class AuditDecisionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    source_pdf_sha256: str
    auditor: str
    decisions: list[AuditDecision]

    @field_validator("auditor")
    @classmethod
    def auditor_is_named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("auditor identity must not be blank")
        return value


class ValidationPaper(BaseModel):
    """Pinned source inputs for the mandatory heterogeneous validation set."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    doi: str | None = None
    pdf_url: str
    supplement_url: str | None = None


class ValidationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: list[ValidationPaper]


class ValidationDecisionBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: list[AuditDecisionSet]


@dataclass(frozen=True)
class ExtractionMetadata:
    provider_path: str
    accepted: list[str]
    rejected: list[str]
    errored: list[str]
    supplement_sha256: str | None = None


@dataclass(frozen=True)
class ExtractedPaper:
    record: PaperRecord
    primary_sha256: str
    metadata: ExtractionMetadata


def _assert_cache_matches_source(pdf_path: Path, extracted: ExtractedPaper) -> None:
    if not pdf_path.exists():
        return
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if digest != extracted.primary_sha256:
        raise ValueError(
            f"cached extraction for {pdf_path.name} was produced from a different "
            f"document (cached {extracted.primary_sha256}, on disk {digest})"
        )


def load_extraction_cache(path: Path) -> dict[str, ExtractedPaper]:
    """Rehydrate a previous run's extracted records.

    Semantic extraction is a paid, non-deterministic network call, so a report
    regenerated from a cache is the only way an auditor without provider
    credentials can reproduce the exact artifacts under review. The cached
    digest is re-checked against the source PDF at use time, so a cache can
    never quietly stand in for a different document.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    cache: dict[str, ExtractedPaper] = {}
    for paper_id, item in payload["papers"].items():
        cache[paper_id] = ExtractedPaper(
            PaperRecord.model_validate(item["record"]),
            item["primary_sha256"],
            ExtractionMetadata(
                item["metadata"]["provider_path"],
                item["metadata"]["accepted"],
                item["metadata"]["rejected"],
                item["metadata"]["errored"],
                item["metadata"].get("supplement_sha256"),
            ),
        )
    return cache


def dump_extraction_cache(cache: dict[str, ExtractedPaper], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "papers": {
            paper_id: {
                "primary_sha256": item.primary_sha256,
                "metadata": {
                    "provider_path": item.metadata.provider_path,
                    "accepted": item.metadata.accepted,
                    "rejected": item.metadata.rejected,
                    "errored": item.metadata.errored,
                    "supplement_sha256": item.metadata.supplement_sha256,
                },
                "record": item.record.model_dump(mode="json"),
            }
            for paper_id, item in cache.items()
        },
    }, indent=2) + "\n", encoding="utf-8")


def _supplement_statement(url: str | None, digest: str | None) -> str:
    """State plainly whether absence in this run could see supplementary material."""
    if url and digest:
        return f"supplementary material was fetched and searched ({url}, SHA-256 `{digest}`)"
    return (
        "no supplementary material was supplied to this run, so every absence below is "
        "scoped to the primary document only"
    )


def _effective_status(field: EvidenceField[Any]) -> str:
    """Do not render a schema default as a scientifically searched absence."""
    if str(field.status) == "NOT_REPORTED" and not field.absence_search_scope:
        return "EXTRACTION_ERROR"
    return str(field.status)


def extract_parsed(
    parsed: ParsedPdf,
    digest: str,
    *,
    semantic_extractor: SemanticExtractor | None = None,
    provider_name: str = "none",
    supplement_digest: str | None = None,
) -> ExtractedPaper:
    deterministic = ScientificExtractor().extract(parsed)
    accepted: list[str] = []
    rejected = list(deterministic.rejected_claims)
    errored: list[str] = []
    provider_path = "deterministic shared rules; semantic disabled"
    if semantic_extractor is not None:
        provider_path = f"deterministic shared rules -> {provider_name} semantic proposals -> evidence/value validation"
        try:
            semantic = semantic_extractor.extract(parsed, deterministic.record)
        except SemanticExtractionError as exc:
            # The report records failure without converting it to absence or
            # losing the deterministic results.
            provider_path += f" (provider failure: {type(exc).__name__})"
            errored = ["semantic-provider-call"]
        else:
            accepted = semantic.accepted
            rejected.extend(semantic.rejected)
            errored = semantic.errored
    return ExtractedPaper(
        deterministic.record,
        digest,
        ExtractionMetadata(
            provider_path, sorted(set(accepted)), sorted(set(rejected)),
            sorted(set(errored)), supplement_digest,
        ),
    )


def field_at(record: PaperRecord, path: str) -> EvidenceField[Any]:
    value: Any = record
    for part in path.split("."):
        value = getattr(value, part)
    return value


def evidence_fields(record: PaperRecord) -> dict[str, EvidenceField[Any]]:
    fields: dict[str, EvidenceField[Any]] = {}

    def walk(model: BaseModel, prefix: str = "") -> None:
        for name in type(model).model_fields:
            value = getattr(model, name)
            path = f"{prefix}{name}"
            if isinstance(value, EvidenceField):
                fields[path] = value
            elif isinstance(value, BaseModel):
                walk(value, f"{path}.")

    walk(record)
    return fields


def prediction_for(golden: GoldenPaper, record: PaperRecord) -> PaperPrediction:
    fields: list[PredictedField] = []
    for expected in golden.fields:
        extracted = field_at(record, expected.path)
        value = extracted.value
        # PaperRecord represents narrative result/limitation fields as lists; the
        # v1 compact benchmark predates that schema and stores a singleton scalar.
        if not isinstance(expected.value, list) and isinstance(value, list) and len(value) == 1:
            value = value[0]
        status = extracted.status
        # A schema default is not an evidence-backed absence assertion. Until a
        # field-specific full-paper and applicable-supplement scope is recorded,
        # benchmark it honestly as an extraction failure.
        if status == "NOT_REPORTED" and not extracted.absence_search_scope:
            status = "EXTRACTION_ERROR"
        fields.append(PredictedField(
            path=expected.path, value=value,
            conflict_values=extracted.conflict_values, status=status,
            source=extracted.source, sources=extracted.sources,
        ))
    return PaperPrediction(paper_id=golden.paper.id, fields=fields)


def render_audit(
    paper: GoldenPaper,
    record: PaperRecord,
    digest: str,
    decisions: AuditDecisionSet | None = None,
    supplement_statement: str | None = None,
) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return "—"
        rendered = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        rendered = "".join(character for character in rendered if character.isprintable())
        if len(rendered) > 500:
            rendered = rendered[:497].rstrip() + "..."
        return rendered.replace("|", "\\|").replace("\n", " ")

    if decisions is not None:
        if decisions.paper_id != paper.paper.id or decisions.source_pdf_sha256 != digest:
            raise ValueError("auditor decisions do not match the paper ID and PDF digest")
        decision_paths = [decision.path for decision in decisions.decisions]
        if len(decision_paths) != len(set(decision_paths)):
            raise ValueError("auditor decision paths must be unique")
        if set(decision_paths) != set(AUDIT_PATHS):
            raise ValueError("auditor decisions must cover every human-audit field")
    by_path = {decision.path: decision for decision in decisions.decisions} if decisions else {}
    golden_by_path = {item.path: item for item in paper.fields}
    statuses = [_effective_status(field_at(record, path)) for path in AUDIT_PATHS]
    counts = {
        status: statuses.count(status)
        for status in ("NOT_VERIFIED", "NOT_REPORTED", "CONFLICT", "EXTRACTION_ERROR")
    }
    rows = [
        "# 4DVarNet-SSH extraction audit",
        "",
        f"Primary PDF: [{paper.paper.pdf_url}]({paper.paper.pdf_url})  ",
        f"SHA-256: `{digest}`  ",
        f"Supplement coverage: {supplement_statement or 'no supplementary material was supplied to this run'}.  ",
        "Targeted fields: **{total}**; populated: **{NOT_VERIFIED}**; `NOT_REPORTED`: **{NOT_REPORTED}**; "
        "`CONFLICT`: **{CONFLICT}**; `EXTRACTION_ERROR`: **{EXTRACTION_ERROR}**.  ".format(
            total=len(AUDIT_PATHS), **counts,
        ),
        (f"Independent auditor: `{decisions.auditor}`." if decisions else "Extraction status is pre-audit. `PENDING_INDEPENDENT_AUDIT` must be replaced only from an auditor-authored decision artifact."),
        "",
        "| Field path | Extracted value | Status | Provenance | Origin | Page | Section | Evidence snippet | Evidence URL | Absence search scope | Golden expected value | Implementation pre-flight | Pre-flight mismatch reason | Independent auditor decision | Auditor evidence location | Auditor reason |",
        "|---|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|",
    ]
    for path in AUDIT_PATHS:
        item = field_at(record, path)
        value = item.conflict_values if item.status == "CONFLICT" else item.value
        decision = by_path.get(path)
        golden = golden_by_path.get(path)
        effective_status = _effective_status(item)
        expected = None if golden is None else (
            golden.conflict_values if str(golden.status) == "CONFLICT" else golden.value
        )
        if golden is None:
            preflight, mismatch = "NOT_AUDITED", "No audited golden label exists for this path."
        elif str(golden.status) == "VERIFIED":
            exact = (
                effective_status == "NOT_VERIFIED"
                and json.dumps(value, sort_keys=True) == json.dumps(expected, sort_keys=True)
                and item.source.is_locatable
            )
            preflight = "PASS" if exact else "FAIL"
            mismatch = "—" if exact else "Value/status/evidence does not exactly match the audited golden label."
        elif str(golden.status) == "CONFLICT":
            exact = (
                effective_status == "CONFLICT"
                and {json.dumps(v, sort_keys=True) for v in item.conflict_values}
                == {json.dumps(v, sort_keys=True) for v in golden.conflict_values}
            )
            preflight = "PASS" if exact else "FAIL"
            mismatch = "—" if exact else "Conflict alternatives do not exactly match the audited golden label."
        else:
            exact = effective_status == "NOT_REPORTED" and bool(item.absence_search_scope)
            preflight = "PASS" if exact else "FAIL"
            mismatch = "—" if exact else "Absence was not established with a documented adequate search scope."
        rows.append(
            "| " + " | ".join((
                path, cell(value), effective_status, str(item.provenance_type),
                str(item.source.origin) if item.source.is_supplied else "—",
                cell(item.source.page), cell(item.source.section),
                cell(item.source.evidence), cell(item.source.evidence_url),
                cell("; ".join(item.absence_search_scope) or None),
                cell(expected), preflight, mismatch,
                decision.decision if decision else "PENDING_INDEPENDENT_AUDIT",
                cell(decision.evidence_location) if decision else "—",
                cell(decision.reason) if decision else "—",
            )) + " |"
        )
    rows.extend((
        "", "## Status interpretation", "",
        "- `NOT_VERIFIED`: a claim passed the literal page-evidence gate but has not been scientifically certified.",
        "- `NOT_REPORTED`: asserted only when a field-specific lexical absence probe found none of the field's reporting vocabulary in the searched scope; the scope that establishes it is printed in its own column.",
        "- `EXTRACTION_ERROR`: a configured claim could not be grounded at its expected source location; it is not treated as absence.",
        "", "Generated by `ocean-research-hub-real-pdf-benchmark`; do not edit extracted values by hand.", "",
    ))
    return "\n".join(rows)


def render_validation_report(
    results: list[tuple[ValidationPaper, PaperRecord, str]],
    decisions: ValidationDecisionBundle | None = None,
    metadata_by_paper: dict[str, ExtractionMetadata] | None = None,
    golden_by_paper: dict[str, GoldenPaper] | None = None,
) -> str:
    """Render source-grounded claims without pretending developer review is audit."""

    decision_sets = {item.paper_id: item for item in decisions.papers} if decisions else {}
    audit_state = (
        "Independent decisions supplied; rows without a decision remain pending."
        if decisions else
        "`PENDING_INDEPENDENT_AUDIT` is intentional until an auditor-authored decision bundle is supplied."
    )
    rows = [
        "# Issue #19 four-paper extraction validation",
        "",
        f"Every row is generated from parsed source evidence. {audit_state}",
        "",
    ]
    for paper, record, digest in results:
        metadata = (metadata_by_paper or {}).get(
            paper.id,
            ExtractionMetadata("deterministic shared rules; semantic disabled", [], [], []),
        )
        decision_set = decision_sets.get(paper.id)
        if decision_set and decision_set.source_pdf_sha256 != digest:
            raise ValueError(f"auditor decisions do not match PDF digest for {paper.id}")
        by_path = {
            decision.path: decision for decision in decision_set.decisions
        } if decision_set else {}
        golden_fields = {
            field.path: field
            for field in (golden_by_paper or {}).get(paper.id, GoldenPaper).fields
        } if paper.id in (golden_by_paper or {}) else {}
        fields = evidence_fields(record)
        paths = list(AUDIT_PATHS)
        statuses = [_effective_status(fields[path]) for path in paths]
        populated = sum(status == "NOT_VERIFIED" for status in statuses)
        conflicts = sum(status == "CONFLICT" for status in statuses)
        not_reported = sum(status == "NOT_REPORTED" for status in statuses)
        extraction_errors = sum(status == "EXTRACTION_ERROR" for status in statuses)
        rows.extend((
            f"## {paper.title}",
            "",
            f"Paper ID: `{paper.id}`  ",
            f"DOI: `{paper.doi}`  " if paper.doi else "DOI: not reported  ",
            f"Primary PDF: [{paper.pdf_url}]({paper.pdf_url})  ",
            f"SHA-256: `{digest}`  ",
            (f"Supplement: [{paper.supplement_url}]({paper.supplement_url})  " if paper.supplement_url else "Supplement: not supplied  "),
            (f"Supplement SHA-256: `{metadata.supplement_sha256}`  " if metadata.supplement_sha256 else "Supplement SHA-256: not available  "),
            f"Extraction provider/path: `{metadata.provider_path}`  ",
            f"Targeted fields: **{len(paths)}**; populated: **{populated}**; `NOT_REPORTED`: **{not_reported}**; `EXTRACTION_ERROR`: **{extraction_errors}**; conflicts: **{conflicts}**; unsupported proposals rejected: **{len(metadata.rejected)}**.  ",
            f"Semantic accepted: **{len(metadata.accepted)}**; semantic/unresolved errors: **{len(metadata.errored)}**.  ",
            "",
            "| Field path | Extracted value | Status | Provenance | Origin | Page | Section | Exact evidence | Evidence URL/origin | Absence search scope | Golden expected value | Implementation pre-flight | Pre-flight mismatch reason | Independent auditor decision | Auditor reason |",
            "|---|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|",
        ))
        for path in paths:
            field = fields[path]
            decision = by_path.get(path)
            value = field.conflict_values if field.status == "CONFLICT" else field.value
            golden = golden_fields.get(path)
            if golden is None:
                expected, preflight = None, "NOT_AUDITED"
                preflight_reason = "No audited golden label exists for this path."
            else:
                expected = golden.conflict_values if str(golden.status) == "CONFLICT" else golden.value
                if str(golden.status) == "VERIFIED":
                    matched = (
                        _effective_status(field) == "NOT_VERIFIED"
                        and json.dumps(value, sort_keys=True) == json.dumps(expected, sort_keys=True)
                        and field.source.is_locatable
                    )
                elif str(golden.status) == "CONFLICT":
                    matched = (
                        _effective_status(field) == "CONFLICT"
                        and {json.dumps(v, sort_keys=True) for v in field.conflict_values}
                        == {json.dumps(v, sort_keys=True) for v in golden.conflict_values}
                    )
                else:
                    matched = (
                        _effective_status(field) == "NOT_REPORTED"
                        and bool(field.absence_search_scope)
                    )
                preflight = "PASS" if matched else "FAIL"
                preflight_reason = "—" if matched else "Extracted value/status/evidence does not exactly match the audited golden label."
            cells = (
                path,
                value,
                _effective_status(field),
                field.provenance_type,
                field.source.origin if field.source.is_supplied else None,
                field.source.page if field.source.is_supplied else None,
                field.source.section if field.source.is_supplied else None,
                field.source.evidence if field.source.is_supplied else None,
                field.source.evidence_url if field.source.is_supplied else None,
                "; ".join(field.absence_search_scope) or None,
                expected,
                preflight,
                preflight_reason,
                decision.decision if decision else (
                    "NOT_AUDITED" if decisions is not None else "PENDING_INDEPENDENT_AUDIT"
                ),
                decision.reason if decision else None,
            )
            rendered = []
            for cell_value in cells:
                text = "—" if cell_value is None else (
                    cell_value if isinstance(cell_value, str)
                    else json.dumps(cell_value, ensure_ascii=False, default=str)
                )
                rendered.append(text.replace("|", "\\|").replace("\n", " "))
            rows.append("| " + " | ".join(rendered) + " |")
        rows.extend(("",))
    rows.append("Generated by `ocean-research-hub-real-pdf-benchmark` from the exact source PDFs above.")
    rows.append("")
    return "\n".join(rows)


def validation_json_artifact(
    results: list[tuple[ValidationPaper, PaperRecord, str]],
    metadata_by_paper: dict[str, ExtractionMetadata],
) -> dict[str, Any]:
    """Machine-readable handoff; contains evidence, not developer conclusions."""
    papers: list[dict[str, Any]] = []
    for paper, record, digest in results:
        metadata = metadata_by_paper[paper.id]
        fields: list[dict[str, Any]] = []
        for path in AUDIT_PATHS:
            field = field_at(record, path)
            item = field.model_dump(mode="json")
            item["status"] = _effective_status(field)
            fields.append({"path": path, **item})
        papers.append({
            "id": paper.id,
            "title": paper.title,
            "doi": paper.doi,
            "primary_pdf_url": paper.pdf_url,
            "primary_pdf_sha256": digest,
            "supplement_url": paper.supplement_url,
            "supplement_sha256": metadata.supplement_sha256,
            "provider_path": metadata.provider_path,
            "accepted_paths": metadata.accepted,
            "rejected_paths": metadata.rejected,
            "errored_paths": metadata.errored,
            "fields": fields,
        })
    return {"schema_version": 1, "audit_state": "PENDING_INDEPENDENT_AUDIT", "papers": papers}


def run_validation(
    pdf_dir: Path,
    manifest: ValidationManifest,
    decisions: ValidationDecisionBundle | None = None,
    *,
    semantic_extractor: SemanticExtractor | None = None,
    provider_name: str = "none",
    cache: dict[str, ExtractedPaper] | None = None,
    json_out: Path | None = None,
    golden_by_paper: dict[str, GoldenPaper] | None = None,
) -> str:
    results: list[tuple[ValidationPaper, PaperRecord, str]] = []
    metadata: dict[str, ExtractionMetadata] = {}
    for paper in manifest.papers:
        if cache is not None and paper.id in cache:
            extracted = cache[paper.id]
            _assert_cache_matches_source(pdf_dir / f"{paper.id}.pdf", extracted)
            results.append((paper, extracted.record, extracted.primary_sha256))
            metadata[paper.id] = extracted.metadata
            continue
        target = pdf_dir / f"{paper.id}.pdf"
        if not target.exists():
            with urllib.request.urlopen(paper.pdf_url, timeout=120) as response:
                target.write_bytes(response.read())
        content = target.read_bytes()
        parsed = PdfParser().parse(content, source_name=target.name)
        supplement_digest: str | None = None
        if paper.supplement_url:
            supplement_target = pdf_dir / f"{paper.id}-supplement.pdf"
            if not supplement_target.exists():
                with urllib.request.urlopen(paper.supplement_url, timeout=120) as response:
                    supplement_target.write_bytes(response.read())
            supplement_content = supplement_target.read_bytes()
            supplement_digest = hashlib.sha256(supplement_content).hexdigest()
            supplement = PdfParser().parse(supplement_content, source_name=supplement_target.name)
            parsed = replace(
                parsed,
                supplementary_pages=supplement.pages,
                supplementary_search_scope=[paper.supplement_url],
            )
        extracted = extract_parsed(
            parsed, hashlib.sha256(content).hexdigest(),
            semantic_extractor=semantic_extractor, provider_name=provider_name,
            supplement_digest=supplement_digest,
        )
        if cache is not None:
            cache[paper.id] = extracted
        results.append((paper, extracted.record, extracted.primary_sha256))
        metadata[paper.id] = extracted.metadata
    report = render_validation_report(results, decisions, metadata, golden_by_paper)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(validation_json_artifact(results, metadata), indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def run(
    pdf_dir: Path,
    golden_dir: Path,
    audit_decisions: AuditDecisionSet | None = None,
    *,
    semantic_extractor: SemanticExtractor | None = None,
    provider_name: str = "none",
    cache: dict[str, ExtractedPaper] | None = None,
) -> tuple[PredictionSet, dict[str, Any], str]:
    golden = load_golden(golden_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    predictions: list[PaperPrediction] = []
    audit = ""
    for paper in golden:
        if cache is not None and paper.paper.id in cache:
            extracted = cache[paper.paper.id]
            _assert_cache_matches_source(pdf_dir / f"{paper.paper.id}.pdf", extracted)
            predictions.append(prediction_for(paper, extracted.record))
            if paper.paper.id == "4dvarnet-ssh-2023":
                audit = render_audit(
                    paper, extracted.record, extracted.primary_sha256, audit_decisions,
                    _supplement_statement(None, extracted.metadata.supplement_sha256),
                )
            continue
        target = pdf_dir / f"{paper.paper.id}.pdf"
        if not target.exists():
            with urllib.request.urlopen(str(paper.paper.pdf_url), timeout=120) as response:
                target.write_bytes(response.read())
        content = target.read_bytes()
        parsed = PdfParser().parse(content, source_name=target.name)
        supplement_digest: str | None = None
        if paper.paper.id == "oceannet-2023":
            supplement_target = pdf_dir / "oceannet-2023-supplement.pdf"
            if not supplement_target.exists():
                with urllib.request.urlopen(OCEANNET_SUPPLEMENT_URL, timeout=120) as response:
                    supplement_target.write_bytes(response.read())
            supplement_content = supplement_target.read_bytes()
            supplement_digest = hashlib.sha256(supplement_content).hexdigest()
            supplement = PdfParser().parse(supplement_content, source_name=supplement_target.name)
            parsed = replace(
                parsed,
                supplementary_pages=supplement.pages,
                supplementary_search_scope=[OCEANNET_SUPPLEMENT_URL],
            )
        extracted = extract_parsed(
            parsed, hashlib.sha256(content).hexdigest(),
            semantic_extractor=semantic_extractor, provider_name=provider_name,
            supplement_digest=supplement_digest,
        )
        if cache is not None:
            cache[paper.paper.id] = extracted
        predictions.append(prediction_for(paper, extracted.record))
        if paper.paper.id == "4dvarnet-ssh-2023":
            audit = render_audit(
                paper, extracted.record, extracted.primary_sha256, audit_decisions,
                _supplement_statement(
                    OCEANNET_SUPPLEMENT_URL if paper.paper.id == "oceannet-2023" else None,
                    supplement_digest,
                ),
            )
    prediction_set = PredictionSet(predictions=predictions)
    report = benchmark(golden, prediction_set).model_dump(mode="json")
    return prediction_set, report, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Run grounded extraction against pinned real golden PDFs")
    parser.add_argument("--pdf-dir", type=Path, default=Path(".data/golden-pdfs"))
    parser.add_argument("--golden-dir", type=Path, default=Path("evaluation/golden_dataset"))
    parser.add_argument("--predictions-out", type=Path, required=True)
    parser.add_argument("--benchmark-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--audit-decisions", type=Path)
    parser.add_argument("--validation-manifest", type=Path)
    parser.add_argument("--validation-report-out", type=Path)
    parser.add_argument("--validation-json-out", type=Path)
    parser.add_argument("--validation-decisions", type=Path)
    parser.add_argument(
        "--extraction-cache", type=Path,
        help="Reuse this run's extracted records, or replay a previous run's cache "
             "to regenerate every report without calling a semantic provider",
    )
    parser.add_argument(
        "--semantic-provider", choices=("none", "claude", "gemini"), default="none",
        help="Explicit semantic proposal provider; default is network-free deterministic extraction",
    )
    args = parser.parse_args()
    load_dotenv()
    semantic_extractor: SemanticExtractor | None = None
    if args.semantic_provider == "claude":
        semantic_extractor = SemanticExtractor(client=AnthropicClient())
    elif args.semantic_provider == "gemini":
        semantic_extractor = SemanticExtractor(client=GeminiClient())
    decisions = (
        AuditDecisionSet.model_validate_json(args.audit_decisions.read_text(encoding="utf-8"))
        if args.audit_decisions else None
    )
    extraction_cache: dict[str, ExtractedPaper] = (
        load_extraction_cache(args.extraction_cache)
        if args.extraction_cache and args.extraction_cache.exists()
        else {}
    )
    predictions, report, audit = run(
        args.pdf_dir, args.golden_dir, decisions,
        semantic_extractor=semantic_extractor,
        provider_name=args.semantic_provider,
        cache=extraction_cache,
    )
    for path in (args.predictions_out, args.benchmark_out, args.audit_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.predictions_out.write_text(predictions.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.benchmark_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.audit_out.write_text(audit, encoding="utf-8")
    if (
        args.validation_manifest or args.validation_report_out
        or args.validation_json_out or args.validation_decisions
    ):
        if not args.validation_manifest or not args.validation_report_out:
            parser.error("--validation-manifest and --validation-report-out are required together")
        manifest = ValidationManifest.model_validate_json(
            args.validation_manifest.read_text(encoding="utf-8")
        )
        validation_decisions = (
            ValidationDecisionBundle.model_validate_json(
                args.validation_decisions.read_text(encoding="utf-8")
            )
            if args.validation_decisions else None
        )
        validation_report = run_validation(
            args.pdf_dir, manifest, validation_decisions,
            semantic_extractor=semantic_extractor,
            provider_name=args.semantic_provider,
            cache=extraction_cache,
            json_out=args.validation_json_out,
            golden_by_paper={paper.paper.id: paper for paper in load_golden(args.golden_dir)},
        )
        args.validation_report_out.parent.mkdir(parents=True, exist_ok=True)
        args.validation_report_out.write_text(validation_report, encoding="utf-8")
    if args.extraction_cache:
        dump_extraction_cache(extraction_cache, args.extraction_cache)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
