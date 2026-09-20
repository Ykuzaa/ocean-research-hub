"""Truthful, provenance-preserving aggregation for the public landing page."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from ocean_research_hub.ingestion.models import PaperWorkflowStatus, StoredPaper
from ocean_research_hub.schemas.paper_record import (
    EvidenceField,
    ProvenanceType,
    SourceEvidence,
    VerificationStatus,
)


class LandingState(StrEnum):
    READY = "ready"
    EMPTY = "empty"
    PARTIAL = "partial"


class LandingPaperReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None
    year: int | None
    workflow_status: PaperWorkflowStatus


class LandingField(BaseModel):
    """A complete scientific field contract; value is never used as a quote."""

    model_config = ConfigDict(extra="forbid")

    path: str
    label: str
    value: Any = None
    conflict_values: list[Any] = Field(default_factory=list)
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    source: SourceEvidence
    sources: list[SourceEvidence] = Field(default_factory=list)
    # The first locatable primary-author source, whether stored in the legacy
    # singular slot or the additional-sources list. UI evidence quotes must use
    # this field rather than assuming ``source`` is populated.
    display_source: SourceEvidence | None = None
    absence_search_scope: list[str] = Field(default_factory=list)
    verified_by: str | None = None
    verified_at: datetime | None = None


class LandingEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: LandingPaperReference
    field: LandingField
    matched_value: str | None = None


class LandingNamedTally(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    papers: int
    items: list[LandingEvidenceItem]
    drilldown_path: str


class LandingFieldTally(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    fields: int
    items: list[LandingEvidenceItem]
    drilldown_path: str


class LandingStatusTally(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    fields: int
    description: str
    items: list[LandingEvidenceItem]
    drilldown_path: str


class LandingYearTally(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    papers_with_extracted_fields: int
    bibliography_only: int
    extracted_papers: list[LandingPaperReference]
    bibliographic_papers: list[LandingPaperReference]
    extracted_drilldown_path: str
    bibliographic_drilldown_path: str


class LandingWorkflowTally(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PaperWorkflowStatus
    papers: int
    items: list[LandingPaperReference]
    drilldown_path: str


class LandingDrilldownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: LandingState
    completeness: LandingCompleteness
    total: int
    offset: int
    limit: int
    evidence_items: list[LandingEvidenceItem] = Field(default_factory=list)
    paper_items: list[LandingPaperReference] = Field(default_factory=list)


class LandingTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: int
    readable_papers: int
    domains: int
    papers_with_extracted_fields: int
    extracted_scientific_fields: int
    scientific_record_fields: int
    values_with_exact_evidence: int
    audited_fields: int


class LandingCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_records: int = 0
    message: str | None = None


class LandingExtractionDemo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: LandingPaperReference
    fields: list[LandingField]


class LandingConflictDemo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: LandingPaperReference
    field: LandingField


class LandingGapPreview(BaseModel):
    """Explicit non-result: no gap claim is inferred from corpus frequencies."""

    model_config = ConfigDict(extra="forbid")

    label: str = "Product Preview"
    analytics_state: str = "NOT_COMPUTED"
    is_live_analytic: bool = False
    description: str = (
        "Candidate research-gap detection is a Product Preview. This endpoint does not "
        "infer a gap from missing fields, frequencies, or author limitations."
    )


class LandingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: LandingState
    completeness: LandingCompleteness
    totals: LandingTotals
    statuses: list[LandingStatusTally]
    workflows: list[LandingWorkflowTally]
    years: list[LandingYearTally]
    limitations: list[LandingNamedTally]
    sections: list[LandingFieldTally]
    architecture_families: list[LandingNamedTally]
    datasets: list[LandingNamedTally]
    extraction_demo: LandingExtractionDemo | None
    conflict_demo: LandingConflictDemo | None
    gap_preview: LandingGapPreview = Field(default_factory=LandingGapPreview)


SCIENTIFIC_SECTIONS = (
    "scientific_framing",
    "data",
    "architecture",
    "training",
    "objective",
    "evaluation",
    "results",
    "limitations",
)

SECTION_LABELS = {
    "scientific_framing": "Scientific framing",
    "data": "Data",
    "architecture": "Architecture",
    "training": "Training",
    "objective": "Objective and loss",
    "evaluation": "Evaluation",
    "results": "Results",
    "limitations": "Limitations",
}

LIMITATION_LABELS = {
    "author_reported": "Stated by the authors",
    "future_work": "Future work",
    "reproducibility": "Reproducibility",
    "data": "Data",
    "physics": "Physics",
    "generalization": "Generalisation",
    "uncertainty": "Uncertainty",
    "compute": "Compute",
}

STATUS_DESCRIPTIONS = {
    VerificationStatus.EXTRACTION_ERROR: "Extraction failed for this field.",
    VerificationStatus.NOT_VERIFIED: "Extracted but not confirmed by a scientific auditor.",
    VerificationStatus.NOT_REPORTED: (
        "No value is stored; an audited absence includes its searched source scope."
    ),
    VerificationStatus.CONFLICT: "Conflicting source-backed values are preserved.",
    VerificationStatus.PARTIALLY_VERIFIED: "Partially confirmed by a scientific auditor.",
    VerificationStatus.VERIFIED: "Confirmed against source evidence by a scientific auditor.",
}

STATUS_ORDER = (
    VerificationStatus.EXTRACTION_ERROR,
    VerificationStatus.NOT_VERIFIED,
    VerificationStatus.NOT_REPORTED,
    VerificationStatus.CONFLICT,
    VerificationStatus.PARTIALLY_VERIFIED,
    VerificationStatus.VERIFIED,
)

EXTRACTION_PATHS = (
    "training.optimizer",
    "training.learning_rate",
    "training.batch_size",
    "training.epochs_or_steps",
)


def _has_value(field: EvidenceField[Any]) -> bool:
    value = field.value
    return value is not None and value != "" and value != []


def _primary_exact_evidence(field: EvidenceField[Any]) -> bool:
    return any(
        source.is_locatable and source.is_primary_author_source
        for source in (field.source, *field.sources)
    )


def _is_non_error_claim(field: EvidenceField[Any]) -> bool:
    return field.status in {
        VerificationStatus.NOT_VERIFIED,
        VerificationStatus.PARTIALLY_VERIFIED,
        VerificationStatus.VERIFIED,
    }


def _walk(model: BaseModel, prefix: str = "") -> list[tuple[str, EvidenceField[Any]]]:
    found: list[tuple[str, EvidenceField[Any]]] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, EvidenceField):
            found.append((path, value))
        elif isinstance(value, BaseModel):
            found.extend(_walk(value, path))
    return found


def _display_source(
    field: EvidenceField[Any], *, matched_value: str | None = None
) -> SourceEvidence | None:
    sources = tuple(
        source
        for source in (field.source, *field.sources)
        if source.is_locatable and source.is_primary_author_source
    )
    if matched_value is not None and isinstance(field.value, list) and len(field.value) > 1:
        # The evidence schema intentionally reserves claimed_value bindings for
        # conflicts. A non-conflict list therefore has no safe per-item binding:
        # exclude it from named analytics instead of reusing one excerpt for all.
        return None
    return next(iter(sources), None)


def _field(
    path: str, field: EvidenceField[Any], *, matched_value: str | None = None
) -> LandingField:
    display_source = _display_source(field, matched_value=matched_value)
    return LandingField(
        path=path,
        label=path.rsplit(".", 1)[-1].replace("_", " ").capitalize(),
        value=field.value,
        conflict_values=field.conflict_values,
        status=field.status,
        provenance_type=field.provenance_type,
        confidence=field.confidence,
        source=field.source,
        sources=field.sources,
        display_source=display_source,
        absence_search_scope=field.absence_search_scope,
        verified_by=field.verified_by,
        verified_at=field.verified_at,
    )


def _paper(paper: StoredPaper) -> LandingPaperReference:
    return LandingPaperReference(
        id=paper.id,
        title=paper.record.paper.title.value,
        year=paper.record.paper.year.value,
        workflow_status=paper.workflow_status,
    )


def _scientific_fields(paper: StoredPaper) -> list[tuple[str, EvidenceField[Any]]]:
    fields: list[tuple[str, EvidenceField[Any]]] = []
    for section in SCIENTIFIC_SECTIONS:
        fields.extend(_walk(getattr(paper.record, section), section))
    return fields


def _named_tallies(
    papers: list[StoredPaper], path: str, *, dimension: str,
    labels: dict[str, str] | None = None
) -> list[LandingNamedTally]:
    grouped: dict[str, list[LandingEvidenceItem]] = defaultdict(list)
    for paper in papers:
        fields = dict(_walk(paper.record))
        field = fields.get(path)
        if (
            field is None
            or not _has_value(field)
            or field.provenance_type is not ProvenanceType.AUTHOR_REPORTED_FACT
            or not _is_non_error_claim(field)
            or not _primary_exact_evidence(field)
        ):
            continue
        values = field.value if isinstance(field.value, list) else [field.value]
        for value in dict.fromkeys(str(value).strip() for value in values if str(value).strip()):
            if _display_source(field, matched_value=value) is None:
                continue
            grouped[value].append(
                LandingEvidenceItem(
                    paper=_paper(paper),
                    field=_field(path, field, matched_value=value),
                    matched_value=value,
                )
            )
    return sorted(
        (
            LandingNamedTally(
                key=key,
                label=labels.get(key, key) if labels else key,
                papers=len(items),
                items=items[:3],
                drilldown_path=f"/api/landing/drilldown?dimension={dimension}&key={quote(key)}",
            )
            for key, items in grouped.items()
        ),
        key=lambda tally: (-tally.papers, tally.label.casefold()),
    )


def _limitation_tallies(papers: list[StoredPaper]) -> list[LandingNamedTally]:
    tallies: list[LandingNamedTally] = []
    for key, label in LIMITATION_LABELS.items():
        items: list[LandingEvidenceItem] = []
        path = f"limitations.{key}"
        for paper in papers:
            field = dict(_walk(paper.record)).get(path)
            if (
                field is None
                or not _has_value(field)
                or field.provenance_type is not ProvenanceType.AUTHOR_REPORTED_LIMITATION
                or not _is_non_error_claim(field)
                or not _primary_exact_evidence(field)
            ):
                continue
            items.append(LandingEvidenceItem(paper=_paper(paper), field=_field(path, field)))
        if items:
            tallies.append(LandingNamedTally(
                key=key,
                label=label,
                papers=len(items),
                items=items[:3],
                drilldown_path=f"/api/landing/drilldown?dimension=limitation&key={quote(key)}",
            ))
    return sorted(tallies, key=lambda tally: (-tally.papers, tally.label.casefold()))


def _extraction_demo(papers: list[StoredPaper]) -> LandingExtractionDemo | None:
    best: LandingExtractionDemo | None = None
    for paper in papers:
        fields = dict(_walk(paper.record))
        selected = [
            _field(path, fields[path])
            for path in EXTRACTION_PATHS
            if path in fields
            and _has_value(fields[path])
            and fields[path].provenance_type is ProvenanceType.AUTHOR_REPORTED_FACT
            and _is_non_error_claim(fields[path])
            and _primary_exact_evidence(fields[path])
        ]
        candidate = LandingExtractionDemo(paper=_paper(paper), fields=selected)
        if selected and (best is None or len(selected) > len(best.fields)):
            best = candidate
    return best if best is not None and len(best.fields) >= 3 else None


def _conflict_demo(papers: list[StoredPaper]) -> LandingConflictDemo | None:
    for paper in papers:
        for path, field in _scientific_fields(paper):
            if field.status is VerificationStatus.CONFLICT:
                return LandingConflictDemo(paper=_paper(paper), field=_field(path, field))
    return None


def aggregate_landing(
    papers: list[StoredPaper], *, total: int, invalid_records: int, domain_count: int
) -> LandingResponse:
    scientific = {paper.id: _scientific_fields(paper) for paper in papers}
    status_counts: Counter[VerificationStatus] = Counter(
        field.status for fields in scientific.values() for _, field in fields
    )
    section_counts: Counter[str] = Counter()
    status_items: dict[VerificationStatus, list[LandingEvidenceItem]] = defaultdict(list)
    section_items: dict[str, list[LandingEvidenceItem]] = defaultdict(list)
    for fields in scientific.values():
        for path, field in fields:
            if _has_value(field) or field.conflict_values:
                section_counts[path.split(".", 1)[0]] += 1

    for paper in papers:
        for path, field in scientific[paper.id]:
            item = LandingEvidenceItem(paper=_paper(paper), field=_field(path, field))
            status_items[field.status].append(item)
            if _has_value(field) or field.conflict_values:
                section_items[path.split(".", 1)[0]].append(item)

    year_counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    papers_with_fields = 0
    extracted_fields = 0
    exact_evidence = 0
    audited_fields = 0
    for paper in papers:
        fields = scientific[paper.id]
        claims = [field for _, field in fields if _has_value(field) or field.conflict_values]
        if claims:
            papers_with_fields += 1
        extracted_fields += len(claims)
        exact_evidence += sum(
            _has_value(field)
            and _is_non_error_claim(field)
            and field.provenance_type
            in {
                ProvenanceType.AUTHOR_REPORTED_FACT,
                ProvenanceType.AUTHOR_REPORTED_LIMITATION,
            }
            and _primary_exact_evidence(field)
            for _, field in fields
        )
        audited_fields += sum(
            field.status in {VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED}
            for _, field in fields
        )
        year = paper.record.paper.year.value
        if year is not None:
            year_counts[year][0 if claims else 1] += 1

    state = (
        LandingState.PARTIAL
        if invalid_records
        else LandingState.EMPTY
        if total == 0
        else LandingState.READY
    )
    completeness = LandingCompleteness(
        missing_records=invalid_records,
        message=(
            f"{invalid_records} stored record(s) could not be validated and are excluded from aggregates."
            if invalid_records
            else None
        ),
    )
    return LandingResponse(
        state=state,
        completeness=completeness,
        totals=LandingTotals(
            papers=total,
            readable_papers=len(papers),
            domains=domain_count,
            papers_with_extracted_fields=papers_with_fields,
            extracted_scientific_fields=extracted_fields,
            scientific_record_fields=sum(len(fields) for fields in scientific.values()),
            values_with_exact_evidence=exact_evidence,
            audited_fields=audited_fields,
        ),
        statuses=[
            LandingStatusTally(
                status=status,
                fields=status_counts.get(status, 0),
                description=STATUS_DESCRIPTIONS[status],
                items=status_items.get(status, [])[:3],
                drilldown_path=(
                    f"/api/landing/drilldown?dimension=status&key={status.value}"
                ),
            )
            for status in STATUS_ORDER
        ],
        workflows=[
            LandingWorkflowTally(
                status=status,
                papers=len(items),
                items=items[:3],
                drilldown_path=(
                    f"/api/landing/drilldown?dimension=workflow&key={status.value}"
                ),
            )
            for status, items in sorted(
                (
                    (status, [_paper(paper) for paper in papers if paper.workflow_status is status])
                    for status in PaperWorkflowStatus
                ),
                key=lambda item: item[0].value,
            )
            if items
        ],
        years=[
            LandingYearTally(
                year=year,
                papers_with_extracted_fields=counts[0],
                bibliography_only=counts[1],
                extracted_papers=[
                    _paper(paper)
                    for paper in papers
                    if paper.record.paper.year.value == year and scientific[paper.id]
                    and any(_has_value(field) or field.conflict_values for _, field in scientific[paper.id])
                ][:3],
                bibliographic_papers=[
                    _paper(paper)
                    for paper in papers
                    if paper.record.paper.year.value == year
                    and not any(_has_value(field) or field.conflict_values for _, field in scientific[paper.id])
                ][:3],
                extracted_drilldown_path=(
                    f"/api/landing/drilldown?dimension=year_extracted&key={year}"
                ),
                bibliographic_drilldown_path=(
                    f"/api/landing/drilldown?dimension=year_bibliographic&key={year}"
                ),
            )
            for year, counts in sorted(year_counts.items())
        ],
        limitations=_limitation_tallies(papers),
        sections=[
            LandingFieldTally(
                key=key,
                label=SECTION_LABELS[key],
                fields=count,
                items=section_items[key][:3],
                drilldown_path=f"/api/landing/drilldown?dimension=section&key={key}",
            )
            for key, count in sorted(
                section_counts.items(), key=lambda item: (-item[1], SECTION_LABELS[item[0]])
            )
        ],
        architecture_families=_named_tallies(
            papers, "architecture.family", dimension="architecture"
        ),
        datasets=_named_tallies(papers, "data.datasets", dimension="dataset"),
        extraction_demo=_extraction_demo(papers),
        conflict_demo=_conflict_demo(papers),
    )


def landing_drilldown(
    papers: list[StoredPaper], *, corpus_total: int, invalid_records: int,
    dimension: str, key: str, offset: int, limit: int
) -> LandingDrilldownResponse:
    """Return one bounded, traceable slice behind an aggregate count."""
    evidence_items: list[LandingEvidenceItem] = []
    paper_items: list[LandingPaperReference] = []

    for paper in papers:
        fields = _scientific_fields(paper)
        claims = any(_has_value(field) or field.conflict_values for _, field in fields)
        if dimension == "workflow" and paper.workflow_status.value == key:
            paper_items.append(_paper(paper))
        elif dimension in {"year_extracted", "year_bibliographic"}:
            try:
                year = int(key)
            except ValueError:
                continue
            wanted = claims if dimension == "year_extracted" else not claims
            if paper.record.paper.year.value == year and wanted:
                paper_items.append(_paper(paper))

        for path, field in fields:
            include = False
            matched_value: str | None = None
            if dimension == "status" and field.status.value == key:
                include = True
            elif dimension == "section" and path.split(".", 1)[0] == key:
                include = _has_value(field) or bool(field.conflict_values)
            elif dimension == "limitation" and path == f"limitations.{key}":
                include = (
                    _has_value(field)
                    and field.provenance_type is ProvenanceType.AUTHOR_REPORTED_LIMITATION
                    and _is_non_error_claim(field)
                    and _primary_exact_evidence(field)
                )
            elif dimension in {"architecture", "dataset"}:
                wanted_path = "architecture.family" if dimension == "architecture" else "data.datasets"
                values = field.value if isinstance(field.value, list) else [field.value]
                include = (
                    path == wanted_path
                    and key in {str(value).strip() for value in values if value is not None}
                    and field.provenance_type is ProvenanceType.AUTHOR_REPORTED_FACT
                    and _is_non_error_claim(field)
                    and _display_source(field, matched_value=key) is not None
                )
                matched_value = key if include else None
            if include:
                evidence_items.append(
                    LandingEvidenceItem(
                        paper=_paper(paper),
                        field=_field(path, field, matched_value=matched_value),
                        matched_value=matched_value,
                    )
                )

    all_items: list[Any] = evidence_items if evidence_items else paper_items
    page = all_items[offset : offset + limit]
    return LandingDrilldownResponse(
        state=(
            LandingState.PARTIAL
            if invalid_records
            else LandingState.EMPTY
            if corpus_total == 0
            else LandingState.READY
        ),
        completeness=LandingCompleteness(
            missing_records=invalid_records,
            message=(
                f"{invalid_records} stored record(s) could not be validated and are excluded from this drill-down."
                if invalid_records
                else None
            ),
        ),
        total=len(all_items),
        offset=offset,
        limit=limit,
        evidence_items=page if evidence_items else [],
        paper_items=page if paper_items and not evidence_items else [],
    )
