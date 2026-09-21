"""Page/section-aware PDF parsing and evidence-grounded scientific extraction."""

from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel
from pypdf import PdfReader

from ocean_research_hub.schemas.paper_record import (
    EvidenceField, PaperRecord, ProvenanceType, SourceEvidence, SourceOrigin,
    VerificationStatus,
)
from .errors import ParserError


def normalize_text(text: str) -> str:
    """Normalize layout noise while retaining every source word."""
    text = unicodedata.normalize("NFKC", text).replace("−", "-").replace("–", "-")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ParsedBlock:
    page: int
    section: str | None
    locator: str
    text: str


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str
    physical_page: int | None = None
    blocks: list[ParsedBlock] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPdf:
    pages: list[ParsedPage]
    source_name: str
    supplementary_pages: list[ParsedPage] = field(default_factory=list)
    supplementary_search_scope: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


class PdfParser:
    """Replaceable structured parser boundary with publisher page labels.

    pypdf is used because it is local/reproducible and preserves the printed page
    labels required by the evidence model for every current golden PDF. ParsedBlock
    is the compatibility boundary for a later GROBID or Docling provider.
    """

    _heading = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,100})$")

    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        if not content.startswith(b"%PDF"):
            raise ParserError("PDF parser rejected input: file does not have a PDF signature")
        try:
            reader = PdfReader(io.BytesIO(content))
            labels = reader.page_labels
            texts = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:
            raise ParserError(f"PDF parsing failed for {source_name}") from exc
        if not texts or not any(texts):
            raise ParserError(f"PDF parsing produced no extractable text for {source_name}")
        pages: list[ParsedPage] = []
        current_section: str | None = None
        for physical_page, text in enumerate(texts, 1):
            label = labels[physical_page - 1] if physical_page <= len(labels) else str(physical_page)
            # Printed labels are preferable for citations, but page zero is
            # invalid in SourceEvidence; fall back to the physical page.
            page = (
                int(label)
                if str(label).isdigit() and int(label) >= 1
                else physical_page
            )
            blocks: list[ParsedBlock] = []
            buffered: list[str] = []
            buffered_section = current_section

            def flush() -> None:
                nonlocal buffered
                cleaned = normalize_text("\n".join(buffered))
                if not cleaned:
                    buffered = []
                    return
                kind = (
                    "caption"
                    if re.match(r"^(?:Figure|Fig\.|Table)\s+\d+", cleaned)
                    else "paragraph"
                )
                blocks.append(ParsedBlock(
                    page, buffered_section, f"PDF {kind} {len(blocks) + 1}", cleaned,
                ))
                buffered = []

            # pypdf often emits a full page without blank paragraphs. Scan in
            # source order and split at headings so evidence before a later
            # heading is not mislabeled with that later section.
            for line in text.splitlines():
                cleaned_line = normalize_text(line)
                heading = self._heading.match(cleaned_line)
                # Running headers such as ``2124 A. Author et al.`` are not
                # numbered scientific section headings.
                if heading and not (
                    heading.group(1).isdigit() and int(heading.group(1)) == page
                ):
                    flush()
                    current_section = f"{heading.group(1)} {heading.group(2)}"
                    buffered_section = current_section
                    buffered.append(line)
                elif not cleaned_line:
                    flush()
                    buffered_section = current_section
                else:
                    if not buffered:
                        buffered_section = current_section
                    buffered.append(line)
            flush()
            pages.append(ParsedPage(page, text, physical_page, blocks))
        return ParsedPdf(pages, source_name)


@dataclass(frozen=True)
class ExtractionResult:
    record: PaperRecord
    search_scope: list[str]
    warnings: list[str]
    rejected_claims: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceSelector:
    page: int
    section: str
    locator: str
    pattern: str
    require_heading: bool = False
    origin: SourceOrigin = SourceOrigin.PRIMARY_PAPER
    evidence_url: str | None = None


@dataclass(frozen=True)
class ClaimRule:
    path: str
    value: Any
    evidence: tuple[EvidenceSelector, ...]
    limitation: bool = False


class EvidenceValidator:
    """Reject evidence not literally locatable on the declared parsed page."""

    def locate(self, parsed: ParsedPdf, selector: EvidenceSelector) -> SourceEvidence | None:
        pages = (
            parsed.supplementary_pages
            if selector.origin is SourceOrigin.SUPPLEMENTARY_MATERIAL
            else parsed.pages
        )
        page = next((item for item in pages if item.page == selector.page), None)
        if page is None:
            return None
        if selector.require_heading:
            heading = normalize_text(selector.section).lower()
            searchable = normalize_text(page.text).lower()
            if heading not in searchable:
                return None
        match = re.search(selector.pattern, normalize_text(page.text), re.I | re.S)
        if match is None:
            return None
        snippet = match.group(0).strip(" ;:,. ")
        if normalize_text(snippet) not in normalize_text(page.text):
            return None
        return SourceEvidence(
            origin=selector.origin, page=selector.page,
            section=selector.section, locator=selector.locator, evidence=snippet,
            evidence_url=selector.evidence_url,
        )

    MIN_FREE_TEXT_EVIDENCE_LENGTH = 20

    def locate_free_text(
        self, parsed: ParsedPdf, *, page: int, section: str | None, evidence: str,
        origin: SourceOrigin, evidence_url: str | None,
    ) -> SourceEvidence | None:
        """Verify a freely proposed (e.g. LLM-authored) quote against the real page.

        Unlike :meth:`locate`, there is no regex pattern to anchor against: the
        caller supplies the exact snippet it claims is on the page, and this
        independently confirms it is literally present before any value derived
        from it may be stored. A short snippet is rejected outright because a
        few generic words can appear on almost any page by coincidence.
        """
        cleaned = normalize_text(evidence)
        if len(cleaned) < self.MIN_FREE_TEXT_EVIDENCE_LENGTH:
            return None
        pages = (
            parsed.supplementary_pages
            if origin is SourceOrigin.SUPPLEMENTARY_MATERIAL
            else parsed.pages
        )
        located_page = next((item for item in pages if item.page == page), None)
        if located_page is None:
            return None
        if cleaned.lower() not in normalize_text(located_page.text).lower():
            return None
        return SourceEvidence(
            origin=origin, page=page, section=section, locator="LLM-proposed evidence",
            evidence=cleaned, evidence_url=evidence_url,
        )

    @staticmethod
    def supports_normalization(value: Any, sources: list[SourceEvidence]) -> bool:
        """Require every normalized value component to retain source anchors.

        Evidence selectors bind relations; this second gate prevents a selector
        from returning an unrelated stored normalization merely because a paper
        fingerprint or a few generic words matched.
        """
        evidence = " ".join(source.evidence or "" for source in sources).lower()
        expansions = {
            "ssh": "sea surface height", "mse": "mean square error",
            "rmse": "root mean square error", "fno": "fourier neural operator",
            "pec": "predictor evaluate corrector", "relu": "rectified linear unit relu",
            "nr": "nature run", "oi": "optimal interpolation",
        }
        for short, expanded in expansions.items():
            evidence = re.sub(rf"\b{short}\b", f" {expanded} ", evidence)
        months = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
        }
        for month, number in months.items():
            evidence = evidence.replace(month, f"{month} {number}")
        evidence_tokens = set(re.findall(r"[a-z0-9]+", evidence))
        ignored = {
            "a", "an", "and", "as", "at", "by", "for", "from", "in", "is", "of",
            "on", "or", "the", "through", "to", "with", "paper", "reports", "used",
            "fields", "model", "models", "data", "source", "approximately",
        }
        components = value if isinstance(value, list) else [value]
        for component in components:
            tokens = [
                token for token in re.findall(r"[a-z0-9]+", str(component).lower())
                if token not in ignored and (len(token) >= 2 or token.isdigit())
            ]
            if not tokens:
                return False
            matches = sum(token in evidence_tokens for token in tokens)
            # Semantic normalisation is allowed, but weak keyword overlap is
            # not evidence for a composite claim. A majority of the
            # meaningful value tokens must be present in the cited sources.
            required = max(1, math.ceil(len(tokens) * 0.6))
            if matches < required:
                return False
        return True


def resolve_field_target(record: PaperRecord, path: str) -> tuple[BaseModel, str, EvidenceField[Any]]:
    target: BaseModel = record
    parts = path.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    return target, parts[-1], getattr(target, parts[-1])


def set_extracted_field(
    record: PaperRecord, path: str, value: Any, sources: list[SourceEvidence],
    limitation: bool = False,
) -> None:
    """Store an evidence-backed claim, or fork to CONFLICT on a contradicting repeat.

    Shared by every extraction path (deterministic rules, the generic fallback,
    and LLM-proposed claims) so a claim from one mechanism can be recognised as
    contradicting a claim already stored by another.
    """
    target, name, current = resolve_field_target(record, path)
    if current.status is VerificationStatus.CONFLICT:
        alternatives = list(current.conflict_values)
        if value not in alternatives:
            alternatives.append(value)
        bound = sources[0].model_copy(update={"claimed_value": value})
        extra_sources = [
            *current.sources,
            bound,
            *(
                source.model_copy(update={"claimed_value": value})
                for source in sources[1:]
            ),
        ]
        setattr(target, name, current.__class__.model_validate({
            "status": VerificationStatus.CONFLICT,
            "value": None,
            "conflict_values": alternatives,
            "provenance_type": current.provenance_type,
            "confidence": current.confidence,
            "source": current.source,
            "sources": extra_sources,
        }))
        return
    if current.status is VerificationStatus.NOT_VERIFIED and current.value != value:
        old_source = current.source.model_copy(update={"claimed_value": current.value})
        new_source = sources[0].model_copy(update={"claimed_value": value})
        setattr(target, name, current.__class__.model_validate({
            "status": VerificationStatus.CONFLICT, "value": None,
            "conflict_values": [current.value, value],
            "provenance_type": current.provenance_type, "confidence": current.confidence,
            "source": old_source, "sources": [new_source],
        }))
        return
    if current.status is VerificationStatus.NOT_VERIFIED and current.value == value:
        setattr(target, name, current.__class__.model_validate({
            **current.model_dump(),
            "sources": [*current.sources, *sources],
        }))
        return
    setattr(target, name, current.__class__.model_validate({
        "value": value, "status": VerificationStatus.NOT_VERIFIED,
        "provenance_type": ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT,
        "confidence": 0.9, "source": sources[0], "sources": sources[1:],
    }))


def mark_extraction_error(record: PaperRecord, path: str, limitation: bool = False) -> None:
    target, name, current = resolve_field_target(record, path)
    setattr(target, name, current.__class__.model_validate({
        "status": VerificationStatus.EXTRACTION_ERROR,
        "provenance_type": ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT,
    }))


# A lexical absence probe may only be written for a field whose reporting
# vocabulary is near-closed: a paper that reports the field is overwhelmingly
# likely to use one of the listed terms. Narrative fields (the scientific
# problem, dataset inventories, architecture prose, baselines, ablations,
# headline results, author limitations) are deliberately absent from this
# table. The OceanNet supplement is the governing counter-example: it reports
# two ablation experiments without ever writing "ablation", so lexical silence
# there would have produced a false scientific absence. Fields without a probe
# stay EXTRACTION_ERROR, which is the conservative outcome.
ABSENCE_PROBES: dict[str, tuple[str, ...]] = {
    "data.splits.validation": (
        r"\bvalidat", r"\bheld[- ]?out\b", r"\bdevelopment set\b", r"\btuning set\b",
    ),
    "data.preprocessing.missing_data": (
        r"\bmissing\b", r"\bgap", r"\bNaN\b", r"\bincomplete\b", r"\bcloud",
        r"\bfill(?:ed)? value", r"\bunobserved\b", r"\bimput", r"\bdata voids?\b",
    ),
    "data.preprocessing.masking": (
        r"\bmask", r"\bland\b", r"\bcoastline", r"\bocean (?:points|grid points|pixels)\b",
        r"\bover the ocean\b", r"\bvalid (?:points|pixels|values)\b", r"\bexclud",
    ),
    "data.preprocessing.regridding": (
        r"\bre-?grid", r"\bremap", r"\binterpolat", r"\bcoars", r"\bresampl",
        r"\bsubsampl", r"\bupscal", r"\bdownscal", r"\bbilinear\b",
        r"nearest[- ]neighbou?r", r"\bconservative remapping\b",
    ),
    "data.preprocessing.normalization": (
        r"\bnormali[sz]", r"\bstandardi[sz]", r"\bz-?score\b", r"\banomal",
        r"\bdetrend", r"\brescal", r"\bscaled\b", r"\bmin-?max\b",
        r"\bmean[- ]remov", r"\bunit variance\b",
    ),
    "architecture.activations": (
        r"\bactivation", r"\bReLU\b", r"\bGELU\b", r"\btanh\b", r"\bsigmoid\b",
        r"\bSiLU\b", r"\bSwish\b", r"\bsoftplus\b", r"\bsoftmax\b", r"\bELU\b",
        r"\bleaky\b", r"\bnonlinearit", r"\bnon-linearit",
    ),
    "architecture.normalization_layers": (
        r"\bbatch\s*norm", r"\blayer\s*norm", r"\bgroup\s*norm", r"\binstance\s*norm",
        r"normali[sz]ation layer", r"\bBatchNorm\b", r"\bLayerNorm\b", r"\bGroupNorm\b",
        r"\bRMSNorm\b", r"\bweight normali[sz]ation\b",
    ),
    "training.optimizer": (
        r"\boptimi[sz]er\b", r"\bAdam\b", r"\bAdamW\b", r"\bSGD\b", r"\bRMSProp\b",
        r"\bL-?BFGS\b", r"\bAdagrad\b", r"\bAdadelta\b", r"stochastic gradient",
    ),
    "training.learning_rate": (
        r"learning[- ]rate", r"\blearning rates\b", r"\bstep size\b",
    ),
    "training.scheduler": (
        r"\bschedul", r"\bdecay", r"\banneal", r"\bwarm-?up\b", r"\bplateau\b",
        r"\bcosine\b", r"\bstep size\b", r"\bramp",
    ),
    "training.batch_size": (
        r"\bbatch\b", r"\bmini-?batch", r"\bbatches\b",
    ),
    "training.epochs_or_steps": (
        r"\bepoch", r"training (?:steps|iterations)", r"\biteration", r"\bgradient steps\b",
        r"\bupdates\b",
    ),
    "training.hardware": (
        r"\bGPU", r"\bTPU", r"\bCPU", r"\bNVIDIA\b", r"\bA100\b", r"\bV100\b",
        r"\bH100\b", r"\bP100\b", r"\bcluster\b", r"\bcompute node", r"\bhardware\b",
        r"\bworkstation\b", r"\bsupercomputer\b",
    ),
    "training.training_time": (
        r"training time", r"wall[- ]?clock", r"time to train", r"\bcomputational cost\b",
        r"\bruntime\b", r"\bGPU-?hours?\b", r"train\w*\s+(?:took|requires?|takes?)\b",
        r"(?:hours|days|minutes)\s+(?:of|to)\s+train",
    ),
    "objective.auxiliary_losses": (
        r"auxiliary", r"\bregulari[sz]", r"\bpenalt", r"loss term", r"additional loss",
        r"second(?:ary)? loss", r"combined loss", r"weighted sum", r"\bconstraint\b",
    ),
    "evaluation.forecast_horizon": (
        r"\bforecast", r"\blead time", r"\bhorizon\b", r"days? ahead",
        r"prediction (?:range|window|window length)",
    ),
}


def probe_absence(parsed: ParsedPdf, path: str) -> list[str] | None:
    """Return a documented absence scope, or ``None`` when absence is unprovable.

    ``None`` means one of two things and the caller must not distinguish them
    in favour of absence: either the field has no near-closed vocabulary to
    probe, or the vocabulary *is* present in the searched text and the field
    therefore failed to extract rather than being unreported.
    """
    patterns = ABSENCE_PROBES.get(path)
    if patterns is None:
        return None
    primary = normalize_text(parsed.text)
    supplement = normalize_text(
        "\n".join(page.text for page in parsed.supplementary_pages)
    )
    searched = f"{primary} {supplement}"
    if any(re.search(pattern, searched, re.I) for pattern in patterns):
        return None
    supplement_scope = (
        "supplementary material searched: "
        + "; ".join(parsed.supplementary_search_scope)
        + f" ({len(parsed.supplementary_pages)} extractable pages)"
        if parsed.supplementary_search_scope
        else "no supplementary material was supplied to this run; "
        "absence is scoped to the primary document only"
    )
    return [
        f"full text of all {len(parsed.pages)} extractable pages of {parsed.source_name}",
        "field-specific lexical absence probe found no occurrence of any of: "
        + ", ".join(patterns),
        supplement_scope,
    ]


def resolve_absences(record: PaperRecord, parsed: ParsedPdf) -> list[str]:
    """Convert unresolved fields into a documented absence where provable.

    Runs last, after every extraction path has had its chance, so an absence is
    only asserted for a field no mechanism populated. A field left unresolved
    without a provable absence keeps ``EXTRACTION_ERROR``: a failure to extract
    is never reported as the paper not reporting the value.
    """
    asserted: list[str] = []
    for path in ABSENCE_PROBES:
        target, name, current = resolve_field_target(record, path)
        if current.status not in {
            VerificationStatus.NOT_REPORTED, VerificationStatus.EXTRACTION_ERROR,
        }:
            continue
        scope = probe_absence(parsed, path)
        if scope is None:
            if current.status is VerificationStatus.NOT_REPORTED:
                mark_extraction_error(record, path, path.startswith("limitations."))
            continue
        setattr(target, name, current.__class__.model_validate({
            "status": VerificationStatus.NOT_REPORTED,
            "value": None,
            "provenance_type": current.provenance_type,
            "confidence": 0.6,
            "absence_search_scope": scope,
        }))
        asserted.append(path)
    return sorted(asserted)


def iter_evidence_fields(record: PaperRecord) -> Iterable[EvidenceField[Any]]:
    def walk(model: BaseModel) -> Iterable[EvidenceField[Any]]:
        for name in type(model).model_fields:
            value = getattr(model, name)
            if isinstance(value, EvidenceField):
                yield value
            elif isinstance(value, BaseModel):
                yield from walk(value)
    return walk(record)


class ScientificExtractor:
    """Deterministic extractor whose populated claims must pass the evidence gate."""

    def __init__(self, *, evidence_validator: EvidenceValidator | None = None) -> None:
        self.validator = evidence_validator or EvidenceValidator()

    def extract(self, parsed: ParsedPdf) -> ExtractionResult:
        record, warnings = PaperRecord(), []
        rejected = self._generic_extract(record, parsed)
        if rejected:
            warnings.append(
                "deterministic candidates rejected as ambiguous or non-identity claims: "
                + ", ".join(sorted(rejected))
            )
        if not any(field.status is VerificationStatus.NOT_VERIFIED for field in self._fields(record)):
            warnings.append("scientific extraction found no explicit supported claims")
        scope = [
            f"all {len(parsed.pages)} extractable PDF pages",
            "page labels, section headings, paragraphs, captions, and tables exposed by the parser",
            "all shared deterministic capture rules; no paper-specific value registry was used",
            "supplementary material was not searched" if not parsed.supplementary_search_scope else "supplementary search: " + "; ".join(parsed.supplementary_search_scope),
        ]
        resolve_absences(record, parsed)
        return ExtractionResult(record, scope, warnings, sorted(rejected))

    @staticmethod
    def _target(record: PaperRecord, path: str) -> tuple[BaseModel, str, EvidenceField[Any]]:
        return resolve_field_target(record, path)

    @classmethod
    def _set(cls, record: PaperRecord, path: str, value: Any, sources: list[SourceEvidence], limitation: bool = False) -> None:
        set_extracted_field(record, path, value, sources, limitation)

    @classmethod
    def _mark_error(cls, record: PaperRecord, path: str, limitation: bool = False) -> None:
        mark_extraction_error(record, path, limitation)

    @classmethod
    def _generic_extract(cls, record: PaperRecord, parsed: ParsedPdf) -> set[str]:
        rejected: set[str] = set()
        pages = [
            (page, SourceOrigin.PRIMARY_PAPER) for page in parsed.pages
        ] + [
            (page, SourceOrigin.SUPPLEMENTARY_MATERIAL)
            for page in parsed.supplementary_pages
        ]
        for page, origin in pages:
            text = normalize_text(page.text)
            mappings = (
                # Bind the value to explicit use in the reported experiments;
                # a bare optimizer mention in related work is not a claim.
                (r"(?:\bwe\b[^.;]{0,100}?\b(?:use|used|employ|employed)\b|\b(?:training|experiments?|reproduction)\b[^.;]{0,100}?\b(?:use|used|employ|employed)\b)[^.;]{0,100}?\b(AdamW|Adam|SGD|RMSProp)(?:\s*\[[^\]]+\])?\s+optimizer\b", "training.optimizer", str),
                (r"(?:initial\s+)?learning rate\s+(?:of|is|was|=|:)\s*([0-9.eE×^−-]+)", "training.learning_rate", str),
                (r"batch size\s+(?:of|is|was|=|:)\s*([0-9]+)", "training.batch_size", int),
                (r"(?:trained (?:for|over)|for)\s+([0-9]+\s+(?:epochs?|steps?|iterations?))", "training.epochs_or_steps", str),
                (r"weight decay\s+(?:of|is|was|=|:)\s*([0-9.eE×^−-]+)", "training.weight_decay", str),
                (r"dropout(?: rate)?\s+(?:of|is|was|=|:)\s*(0(?:\.\d+)?|1(?:\.0+)?)", "architecture.dropout", float),
                # Scope/evaluation phrases such as "loss is computed on" and
                # "loss was also tested" do not identify a loss function.
                (r"loss function\s+used\s+is\s+([^.;]{3,120})(?:\.(?=\s|$)|;)", "objective.primary_loss", str),
            )
            for pattern, path, value_type in mappings:
                match = re.search(pattern, text, re.I)
                if match:
                    context = text[max(0, match.start() - 140):min(len(text), match.end() + 80)]
                    if path in {
                        "training.learning_rate", "training.batch_size",
                        "training.epochs_or_steps", "training.weight_decay",
                        "architecture.dropout",
                    } and (
                        re.search(r"\b(?:baseline|related work|for comparison)\b", context, re.I)
                        or not re.search(
                            r"\b(?:we|our|training|trained|model|network|experiments?|"
                            r"optimization|optimizer)\b", context, re.I,
                        )
                    ):
                        rejected.add(path)
                        continue
                    value: Any = match.group(1).strip(" ;:,. ")
                    if path == "objective.primary_loss" and re.fullmatch(
                        r"(?:the\s+)?mean square error\s*\(MSE\)(?:\s+loss)?",
                        value, re.I,
                    ):
                        value = "mean square error (MSE)"
                    if value_type is int:
                        value = int(value)
                    elif value_type is float:
                        value = float(value)
                    evidence_match = match
                    if path == "training.optimizer":
                        optimizer_match = re.search(
                            r"\b(?:AdamW|Adam|SGD|RMSProp)(?:\s*\[[^\]]+\])?\s+optimizer\b",
                            match.group(0), re.I,
                        )
                        if optimizer_match is not None:
                            evidence_match = optimizer_match
                    cls._set(record, path, value, [cls._source(
                        page, evidence_match, origin,
                        evidence_url=(
                            parsed.supplementary_search_scope[0]
                            if origin is SourceOrigin.SUPPLEMENTARY_MATERIAL
                            and len(parsed.supplementary_search_scope) == 1
                            else None
                        ),
                    )])
            resolution_match = re.search(
                r"(?:spatial|horizontal) resolution\s+(?:of|is|was|=|:)\s*"
                r"(.+?)(?:\.(?=\s|$)|;)", text, re.I,
            )
            if resolution_match:
                rejected.add("data.spatial_resolution")
            family_match = re.search(
                r"\b(hierarchical transformer|Fourier neural operator|"
                r"convolutional neural network|convolutional LSTM|"
                r"graph neural network|U-?Net)\b",
                text, re.I,
            )
            if family_match:
                context_start = max(0, family_match.start() - 120)
                context_end = min(len(text), family_match.end() + 120)
                context = text[context_start:context_end]
                if re.search(r"\b(?:baseline|related work|for comparison|compared (?:to|with))\b", context, re.I):
                    rejected.add("architecture.family")
                    continue
                rejected.add("architecture.family")
            if (
                re.search(r"(?:loss function|training loss)", text, re.I)
                and record.objective.primary_loss.value is None
            ):
                rejected.add("objective.primary_loss")
        return rejected

    @staticmethod
    def _source(
        page: ParsedPage, match: re.Match[str], origin: SourceOrigin,
        evidence_url: str | None = None,
    ) -> SourceEvidence:
        snippet = match.group(0)
        block = next(
            (
                candidate for candidate in page.blocks
                if normalize_text(snippet) in normalize_text(candidate.text)
            ),
            None,
        )
        return SourceEvidence(
            origin=origin,
            page=page.page,
            section=block.section if block else None,
            locator=block.locator if block else "PDF page text",
            evidence=snippet,
            evidence_url=evidence_url,
        )

    @staticmethod
    def _fields(record: PaperRecord) -> Iterable[EvidenceField[Any]]:
        return iter_evidence_fields(record)


def read_pdf_path(path: str) -> tuple[bytes, str]:
    candidate = Path(path)
    try:
        return candidate.read_bytes(), candidate.name
    except (OSError, ValueError) as exc:
        raise ParserError(f"could not read PDF path: {path}") from exc
