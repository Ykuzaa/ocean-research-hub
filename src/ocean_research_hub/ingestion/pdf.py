"""Page-aware PDF parsing and conservative scientific field extraction.

The extractor is intentionally deterministic.  It only creates a claim when a
sentence contains an explicit cue and preserves the surrounding sentence as
evidence.  It does not fill architecture or training conventions by inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from ocean_research_hub.schemas.paper_record import (
    EvidenceField,
    PaperRecord,
    ProvenanceType,
    SourceEvidence,
    SourceOrigin,
    TextField,
    TextListField,
    IntegerField,
    VerificationStatus,
)

from .errors import ParserError


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str


@dataclass(frozen=True)
class ParsedPdf:
    pages: list[ParsedPage]
    source_name: str

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


class PdfParser:
    """Replaceable parser boundary; GROBID can implement the same contract."""

    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        if not content.startswith(b"%PDF"):
            raise ParserError("PDF parser rejected input: file does not have a PDF signature")
        try:
            reader = PdfReader(__import__("io").BytesIO(content))
            pages = [ParsedPage(index, (page.extract_text() or "").strip()) for index, page in enumerate(reader.pages, 1)]
        except Exception as exc:
            raise ParserError(f"PDF parsing failed for {source_name}") from exc
        if not pages or not any(page.text for page in pages):
            raise ParserError(f"PDF parsing produced no extractable text for {source_name}")
        return ParsedPdf(pages=pages, source_name=source_name)


@dataclass(frozen=True)
class ExtractionResult:
    record: PaperRecord
    search_scope: list[str]
    warnings: list[str]


_SECTION = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?(.{3,100})$", re.MULTILINE)


class ScientificExtractor:
    """Extract explicit claims without converting plausibility into fact."""

    def extract(self, parsed: ParsedPdf) -> ExtractionResult:
        record = PaperRecord()
        warnings: list[str] = []
        for page in parsed.pages:
            for sentence in self._sentences(page.text):
                self._extract_sentence(record, sentence, page.page, self._section(page.text, sentence))
        if not any(field.status is not VerificationStatus.NOT_REPORTED for field in self._fields(record)):
            warnings.append("scientific extraction found no explicit supported claims")
        return ExtractionResult(
            record=record,
            search_scope=["all extractable PDF page text", "paragraphs, headings, captions, and tables as exposed by the parser"],
            warnings=warnings,
        )

    @staticmethod
    def _sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", normalized) if len(part.strip()) >= 12]

    @staticmethod
    def _section(page_text: str, sentence: str) -> str | None:
        before = page_text.split(sentence, 1)[0] if sentence in page_text else ""
        candidates = [match.group(1).strip() for match in _SECTION.finditer(before[-400:])]
        return candidates[-1] if candidates else None

    @staticmethod
    def _source(page: int, section: str | None, sentence: str) -> SourceEvidence:
        return SourceEvidence(
            origin=SourceOrigin.PRIMARY_PAPER,
            page=page,
            section=section,
            locator="PDF extracted paragraph",
            evidence=sentence,
        )

    @classmethod
    def _field(cls, value: Any, page: int, section: str | None, sentence: str, *, list_value: bool = False, limitation: bool = False) -> EvidenceField[Any]:
        return (TextListField if list_value else TextField)(
            value=value,
            status=VerificationStatus.NOT_VERIFIED,
            provenance_type=(ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT),
            confidence=0.8,
            source=cls._source(page, section, sentence),
        )

    @classmethod
    def _set(cls, record: PaperRecord, path: str, value: Any, page: int, section: str | None, sentence: str, *, list_value: bool = False, limitation: bool = False) -> None:
        parts = path.split(".")
        target = record
        for part in parts[:-1]:
            target = getattr(target, part)
        name = parts[-1]
        current = getattr(target, name)
        new_source = cls._source(page, section, sentence)
        if current.status is VerificationStatus.NOT_REPORTED:
            field_type = IntegerField if type(value) is int else (TextListField if list_value else TextField)
            setattr(target, name, field_type(
                value=value,
                status=VerificationStatus.NOT_VERIFIED,
                provenance_type=(ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT),
                confidence=0.8,
                source=new_source,
            ))
        elif current.status is VerificationStatus.CONFLICT:
            if value not in current.conflict_values:
                alternatives = [*current.conflict_values, value]
                new_source.claimed_value = value
                setattr(target, name, current.__class__.model_validate({
                    **current.model_dump(mode="json"),
                    "conflict_values": alternatives,
                    "source": current.source.model_copy(update={"claimed_value": current.conflict_values[0]}),
                    "sources": [*current.sources, new_source],
                }))
        elif current.value != value:
            old_source = current.source.model_copy(update={"claimed_value": current.value})
            new_source.claimed_value = value
            setattr(target, name, current.__class__.model_validate({
                **current.model_dump(mode="json"),
                "value": None,
                "conflict_values": [current.value, value],
                "status": VerificationStatus.CONFLICT,
                "source": old_source,
                "sources": [new_source],
            }))

    @classmethod
    def _extract_sentence(cls, record: PaperRecord, sentence: str, page: int, section: str | None) -> None:
        low = sentence.lower()
        def first(pattern: str) -> str | None:
            match = re.search(pattern, sentence, re.I)
            return match.group(1).strip(" ;:,.") if match else None
        mappings: list[tuple[str, str, bool]] = [
            (r"(?:we|authors) (?:used|utilized|use) (.+?)(?: for training| as (?:the )?input|\.)", "data.datasets", True),
            (r"(?:input|inputs) (?:variables?|data) (?:include|are) (.+?)(?:\.|;)", "data.inputs", True),
            (r"(?:output|outputs) (?:variables?|data) (?:include|are) (.+?)(?:\.|;)", "data.outputs", True),
            (r"(?:trained|training data) (?:from|on|uses?) (.+?)(?:\.|;)", "data.splits.train", False),
            (r"(?:spatial|horizontal) resolution (?:of|is|was) (.+?)(?:\.|;)", "data.spatial_resolution", False),
            (r"(?:temporal|time) resolution (?:of|is|was) (.+?)(?:\.|;)", "data.temporal_resolution", False),
            (r"(?:forecast|prediction) (?:horizon|lead time) (?:of|is|was|ranging from) (.+?)(?:\.|;)", "evaluation.forecast_horizon", False),
            (r"(?:architecture|model) (?:is|uses?|based on|consists of) (.+?)(?:\.|;)", "architecture.summary", False),
            (r"(?:we use|using|with) (?:the )?(AdamW|Adam|SGD|RMSProp) optimizer", "training.optimizer", False),
            (r"learning rate (?:of|is|was) ([0-9.eE×−-]+)", "training.learning_rate", False),
            (r"batch size (?:of|is|was) ([0-9]+)", "training.batch_size", False),
            (r"(?:over|for) ([0-9]+) epochs", "training.epochs_or_steps", False),
            (r"loss function (?:used is|is|was) (.+?)(?:\.|;)", "objective.primary_loss", False),
            (r"(?:evaluation )?metrics? (?:include|are|used) (.+?)(?:\.|;)", "evaluation.metrics", True),
        ]
        for pattern, path, is_list in mappings:
            match = re.search(pattern, sentence, re.I)
            if match:
                value = match.group(1).strip(" ;:,. ")
                if is_list:
                    value = [item.strip() for item in re.split(r",|;| and ", value) if item.strip()]
                expected_list = path.endswith(("datasets", "inputs", "outputs", "metrics"))
                if path == "training.batch_size":
                    value = int(value)
                cls._set(record, path, value, page, section, sentence, list_value=expected_list)

        if any(term in low for term in ("relu", "gelu", "activation function")):
            values = re.findall(r"\b(?:ReLU|GELU|tanh|sigmoid|linear)\b", sentence, re.I)
            if values:
                cls._set(record, "architecture.activations", list(dict.fromkeys(values)), page, section, sentence, list_value=True)
        families = re.findall(r"\b(?:Fourier neural operator|neural operator|hierarchical transformer|transformer|U-?Net|4DVarNet(?:-SSH)?)\b", sentence, re.I)
        if families:
            cls._set(record, "architecture.family", list(dict.fromkeys(families)), page, section, sentence, list_value=True)
        if "limitation" in low or "future work" in low or "remains a challenge" in low:
            cls._set(record, "limitations.author_reported", [sentence], page, section, sentence, list_value=True, limitation=True)

    @staticmethod
    def _fields(record: PaperRecord):
        for model in (record.scientific_framing, record.data, record.architecture, record.training, record.objective, record.evaluation, record.results, record.limitations):
            for value in model.__dict__.values():
                if isinstance(value, EvidenceField):
                    yield value
                elif hasattr(value, "__dict__"):
                    yield from (item for item in value.__dict__.values() if isinstance(item, EvidenceField))


def read_pdf_path(path: str) -> tuple[bytes, str]:
    candidate = Path(path)
    try:
        content = candidate.read_bytes()
    except (OSError, ValueError) as exc:
        raise ParserError(f"could not read PDF path: {path}") from exc
    return content, candidate.name
