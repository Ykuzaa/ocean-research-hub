"""Reproducible real-PDF extraction, benchmark, and audit-report runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ocean_research_hub.evaluation.benchmark import benchmark, load_golden
from ocean_research_hub.evaluation.models import (
    GoldenPaper, PaperPrediction, PredictedField, PredictionSet,
)
from ocean_research_hub.ingestion.pdf import PdfParser, ScientificExtractor
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


def field_at(record: PaperRecord, path: str) -> EvidenceField[Any]:
    value: Any = record
    for part in path.split("."):
        value = getattr(value, part)
    return value


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
    rows = [
        "# 4DVarNet-SSH extraction audit",
        "",
        f"Primary PDF: [{paper.paper.pdf_url}]({paper.paper.pdf_url})  ",
        f"SHA-256: `{digest}`  ",
        "Supplement coverage: not supplied to this PDF-only run; absence claims therefore remain `EXTRACTION_ERROR`.",
        (f"Independent auditor: `{decisions.auditor}`." if decisions else "Extraction status is pre-audit. `PENDING_INDEPENDENT_AUDIT` must be replaced only from an auditor-authored decision artifact."),
        "",
        "| Field path | Extracted value | Status | Provenance | Page | Section | Evidence snippet | Auditor decision | Auditor expected value | Auditor evidence location | Auditor reason |",
        "|---|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for path in AUDIT_PATHS:
        item = field_at(record, path)
        value = item.conflict_values if item.status == "CONFLICT" else item.value
        decision = by_path.get(path)
        rows.append(
            "| " + " | ".join((
                path, cell(value), str(item.status), str(item.provenance_type),
                cell(item.source.page), cell(item.source.section),
                cell(item.source.evidence),
                decision.decision if decision else "PENDING_INDEPENDENT_AUDIT",
                cell(decision.expected_value) if decision else "—",
                cell(decision.evidence_location) if decision else "—",
                cell(decision.reason) if decision else "—",
            )) + " |"
        )
    rows.extend((
        "", "## Status interpretation", "",
        "- `NOT_VERIFIED`: a claim passed the literal page-evidence gate but has not been scientifically certified.",
        "- `NOT_REPORTED`: requires a recorded field-specific full-document and applicable-supplement search scope; this run emits none.",
        "- `EXTRACTION_ERROR`: a configured claim could not be grounded at its expected source location; it is not treated as absence.",
        "", "Generated by `ocean-research-hub-real-pdf-benchmark`; do not edit extracted values by hand.", "",
    ))
    return "\n".join(rows)


def run(
    pdf_dir: Path,
    golden_dir: Path,
    audit_decisions: AuditDecisionSet | None = None,
) -> tuple[PredictionSet, dict[str, Any], str]:
    golden = load_golden(golden_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    predictions: list[PaperPrediction] = []
    audit = ""
    for paper in golden:
        target = pdf_dir / f"{paper.paper.id}.pdf"
        if not target.exists():
            with urllib.request.urlopen(str(paper.paper.pdf_url), timeout=120) as response:
                target.write_bytes(response.read())
        content = target.read_bytes()
        parsed = PdfParser().parse(content, source_name=target.name)
        if paper.paper.id == "oceannet-2023":
            supplement_target = pdf_dir / "oceannet-2023-supplement.pdf"
            if not supplement_target.exists():
                with urllib.request.urlopen(OCEANNET_SUPPLEMENT_URL, timeout=120) as response:
                    supplement_target.write_bytes(response.read())
            supplement = PdfParser().parse(
                supplement_target.read_bytes(), source_name=supplement_target.name
            )
            parsed = replace(
                parsed,
                supplementary_pages=supplement.pages,
                supplementary_search_scope=[OCEANNET_SUPPLEMENT_URL],
            )
        record = ScientificExtractor().extract(parsed).record
        predictions.append(prediction_for(paper, record))
        if paper.paper.id == "4dvarnet-ssh-2023":
            audit = render_audit(
                paper, record, hashlib.sha256(content).hexdigest(), audit_decisions
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
    args = parser.parse_args()
    decisions = (
        AuditDecisionSet.model_validate_json(args.audit_decisions.read_text(encoding="utf-8"))
        if args.audit_decisions else None
    )
    predictions, report, audit = run(args.pdf_dir, args.golden_dir, decisions)
    for path in (args.predictions_out, args.benchmark_out, args.audit_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.predictions_out.write_text(predictions.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.benchmark_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.audit_out.write_text(audit, encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
