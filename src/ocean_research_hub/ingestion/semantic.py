"""LLM-proposed scientific claims, gated by the same evidence rule as everything else.

An LLM may *propose* a value and a supporting quote, but the quote is always
independently re-checked against the actual parsed page text before the value
is allowed to become a stored claim (see :meth:`EvidenceValidator.locate_free_text`).
A proposal whose evidence cannot be located is discarded outright: the model's
own stated confidence is never trusted on its own, matching AGENTS.md rule 1
("never guess") for every extraction path, deterministic or LLM-assisted.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, get_args, get_origin

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from ocean_research_hub.schemas.paper_record import (
    EvidenceField, PaperRecord, ProvenanceType, SourceOrigin, VerificationStatus,
)

from .pdf import (
    EvidenceValidator, ParsedPdf, mark_extraction_error, normalize_text, resolve_field_target,
    set_extracted_field,
)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"


class SemanticExtractionError(RuntimeError):
    """The LLM call itself failed. Never silently treated as field absence."""


class SemanticLLMClient(Protocol):
    """Structural boundary so tests can stub the model without network access."""

    def propose_claims(self, prompt: str) -> str: ...


class GeminiClient:
    """Thin wrapper around the Gemini API used for semantic claim proposal."""

    def __init__(
        self, *, api_key: str | None = None, model: str | None = None,
        timeout_ms: int = 120_000,
    ) -> None:
        # Imported lazily: constructing a GeminiClient is the only thing that
        # should require the google-genai package and an API key at runtime.
        from google import genai
        from google.genai import types

        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise SemanticExtractionError("GEMINI_API_KEY is not set")
        # The SDK has no timeout by default and retries up to 5 times on its
        # own, so a struggling backend can otherwise hang far longer than any
        # caller would expect - an ingestion request must fail visibly
        # (SemanticExtractionError), never hang indefinitely.
        self._client = genai.Client(
            api_key=resolved_key, http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self._model = model or os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    def propose_claims(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.0},
            )
        except Exception as exc:  # any transport/API failure is a hard error, never silent
            raise SemanticExtractionError(f"Gemini request failed: {exc}") from exc
        if not response.text:
            raise SemanticExtractionError("Gemini returned no text content")
        return response.text


class AnthropicClient:
    """Thin wrapper around the Claude API used for semantic claim proposal."""

    def __init__(
        self, *, api_key: str | None = None, model: str | None = None,
        timeout_ms: int = 600_000,
    ) -> None:
        # Imported lazily: constructing an AnthropicClient is the only thing
        # that should require the anthropic package and an API key at runtime.
        import anthropic

        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise SemanticExtractionError("ANTHROPIC_API_KEY is not set")
        # The read timeout bounds the gap *between* streamed events, and the
        # model can think silently for minutes on a long paper before its
        # first visible token (a 180 s read timeout killed a 30-page paper
        # three times in a row). One retry keeps the worst case bounded.
        self._client = anthropic.Anthropic(
            api_key=resolved_key,
            timeout=anthropic.Timeout(timeout_ms / 1000, connect=10.0),
            max_retries=1,
        )
        self._model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self._usage_log = Path(os.environ.get("OCEAN_HUB_LLM_USAGE_LOG", ".data/llm_usage.jsonl"))

    def propose_claims(self, prompt: str) -> str:
        # A paper with many unresolved fields can make Claude generate a long
        # JSON response; a non-streaming call risks the connection-level
        # timeout Anthropic documents for long-running requests. Streaming
        # keeps the connection alive as tokens arrive instead. Opus 5's
        # adaptive thinking is on by default and can consume most of a small
        # max_tokens budget before any visible output is written (observed:
        # 13k+ thinking tokens against a 16k cap on a 92-field extraction,
        # truncating the JSON) - this task is mechanical quote-matching, not
        # deep reasoning, so a lower effort leaves the budget for output.
        try:
            with self._client.messages.stream(
                model=self._model, max_tokens=64000,
                output_config={"effort": "medium"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = stream.get_final_message()
        except Exception as exc:  # any transport/API failure is a hard error, never silent
            raise SemanticExtractionError(f"Claude request failed: {exc}") from exc
        self._log_usage(response)
        if response.stop_reason == "max_tokens":
            raise SemanticExtractionError(
                "Claude response was truncated at the max_tokens limit before completing"
            )
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise SemanticExtractionError("Claude returned no text content")
        return text

    def _log_usage(self, response: Any) -> None:
        """Append token usage so extraction cost is measured, not estimated."""
        usage = response.usage
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "model": response.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
            "stop_reason": response.stop_reason,
        }
        try:
            self._usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self._usage_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # cost accounting must never break an extraction


class _LLMClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    value: JsonValue
    page: int
    section: str | None = None
    evidence: str
    origin: str = "PRIMARY_PAPER"


_TYPE_HINTS: dict[type, str] = {
    str: "string", int: "integer", float: "decimal number", bool: "true or false",
}


def _type_hint(expected_type: Any) -> str:
    if get_origin(expected_type) is list:
        item_type = get_args(expected_type)[0]
        return f"list of {_TYPE_HINTS.get(item_type, 'string')}"
    return _TYPE_HINTS.get(expected_type, "string")


def _coerce_value(raw: JsonValue, expected_type: Any) -> Any | None:
    """Reject anything not shaped like the field's declared type. Never coerce loosely."""
    if get_origin(expected_type) is list:
        item_type = get_args(expected_type)[0]
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list) or not raw:
            return None
        if item_type is str:
            if any(not isinstance(item, str) or not item.strip() for item in raw):
                return None
            return list(raw)
        return None
    if expected_type is str:
        return raw if isinstance(raw, str) and raw.strip() else None
    if expected_type is int:
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else None
    if expected_type is float:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        return None
    if expected_type is bool:
        return raw if isinstance(raw, bool) else None
    return None


_EXTRACTABLE_PROVENANCE = {ProvenanceType.AUTHOR_REPORTED_FACT, ProvenanceType.AUTHOR_REPORTED_LIMITATION}
# Identity-bearing bibliography: a malformed DOI fails ingestion outright, and
# these come from Crossref or the caller rather than from reading the PDF.
_NON_SEMANTIC_PATHS = frozenset({"paper.doi", "paper.arxiv", "paper.urls"})


def field_catalog(record: PaperRecord) -> list[tuple[str, Any]]:
    """Every leaf field path and its declared value type, walked from a live record.

    Title, authors, year and venue are included (a PDF-only ingestion has no
    other source for them); DOI, arXiv id and URLs are not. Fields whose
    default provenance is AI_INTERPRETATION or TEAM_NOTE (e.g.
    ``limitations.ai_interpretation``, ``limitations.team_note``) are always
    excluded: they hold interpretation or human annotation by construction,
    not a literal author claim a PDF quote could ever support.
    """
    catalog: list[tuple[str, Any]] = []

    def walk(model: BaseModel, prefix: str) -> None:
        for name in type(model).model_fields:
            value = getattr(model, name)
            path = f"{prefix}{name}"
            if isinstance(value, EvidenceField):
                if path in _NON_SEMANTIC_PATHS or value.provenance_type not in _EXTRACTABLE_PROVENANCE:
                    continue
                generic_args = type(value).__pydantic_generic_metadata__.get("args")
                expected_type = generic_args[0] if generic_args else str
                catalog.append((path, expected_type))
            elif isinstance(value, BaseModel):
                walk(value, f"{path}.")

    walk(record, "")
    return catalog


def _build_prompt(parsed: ParsedPdf, pending: list[tuple[str, Any]]) -> str:
    fields_block = "\n".join(f"- {path} ({_type_hint(t)})" for path, t in pending)
    primary_block = "\n\n".join(f"[PAGE {page.page}]\n{page.text}" for page in parsed.pages)
    supplement_block = "\n\n".join(
        f"[SUPPLEMENT PAGE {page.page}]\n{page.text}" for page in parsed.supplementary_pages
    )
    supplement_section = (
        f"\n\n--- SUPPLEMENTARY MATERIAL ---\n{supplement_block}" if supplement_block else ""
    )
    return f"""You are extracting structured scientific facts from one research paper for an
evidence-first database. Never guess, never infer an unstated convention, and
never state a value that is not explicitly written in the text below.

For each field below, report a value only if you can quote the EXACT
supporting text verbatim (no paraphrasing, no added punctuation, copy it
character-for-character) as it appears on one specific page shown below. If a
field is not explicitly stated anywhere in the provided text, omit it from
your answer entirely - do not include a null, an empty value, or a guess.

Fields to look for (dotted.path (expected value type)):
{fields_block}

Respond with a JSON array. Each element must have exactly these keys:
{{"path": "<dotted field path, exactly as listed above>",
  "value": <the extracted value, matching the declared type>,
  "page": <printed page number shown in the [PAGE n] / [SUPPLEMENT PAGE n] marker>,
  "section": "<section heading it appears under, or null>",
  "evidence": "<verbatim quoted text from that exact page supporting the value>",
  "origin": "PRIMARY_PAPER" or "SUPPLEMENTARY_MATERIAL"}}

Use "SUPPLEMENTARY_MATERIAL" only when quoting a [SUPPLEMENT PAGE ...] block;
use "PRIMARY_PAPER" for a [PAGE ...] block. Respond with only the JSON array,
no markdown fences, no commentary.

--- PRIMARY PAPER ---
{primary_block}{supplement_section}"""


def _strip_markdown_fence(text: str) -> str:
    """Tolerate a ```json ... ``` wrapper some models add despite instructions not to."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
        elif "```" in stripped:
            stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


@dataclass(frozen=True)
class SemanticExtractionResult:
    accepted: list[str]
    rejected: list[str]
    errored: list[str]


class SemanticExtractor:
    """LLM-proposed claims for schema fields the deterministic pass left unresolved.

    Only runs against fields still at ``NOT_REPORTED`` or ``EXTRACTION_ERROR``
    after the deterministic :class:`~ocean_research_hub.ingestion.pdf.ScientificExtractor`
    pass, so it never overrides or second-guesses an already-matched deterministic
    claim.
    """

    def __init__(self, *, client: SemanticLLMClient, validator: EvidenceValidator | None = None) -> None:
        self.client = client
        self.validator = validator or EvidenceValidator()

    def extract(self, parsed: ParsedPdf, record: PaperRecord) -> SemanticExtractionResult:
        pending = [
            (path, expected_type)
            for path, expected_type in field_catalog(record)
            if resolve_field_target(record, path)[2].status
            in {VerificationStatus.NOT_REPORTED, VerificationStatus.EXTRACTION_ERROR}
        ]
        if not pending:
            return SemanticExtractionResult([], [], [])

        raw = self.client.propose_claims(_build_prompt(parsed, pending))
        try:
            payload = json.loads(_strip_markdown_fence(raw))
        except json.JSONDecodeError as exc:
            raise SemanticExtractionError("semantic extraction returned invalid JSON") from exc
        if isinstance(payload, dict):
            payload = payload.get("claims", [])
        if not isinstance(payload, list):
            raise SemanticExtractionError("semantic extraction did not return a claim list")

        type_by_path = dict(pending)
        accepted: set[str] = set()
        rejected: set[str] = set()
        for item in payload:
            try:
                claim = _LLMClaim.model_validate(item)
            except ValidationError:
                continue
            expected_type = type_by_path.get(claim.path)
            if expected_type is None:
                continue  # not a field we asked about; never let the model invent a path
            value = _coerce_value(claim.value, expected_type)
            try:
                origin = SourceOrigin(claim.origin)
            except ValueError:
                origin = SourceOrigin.PRIMARY_PAPER
            try:
                evidence = (
                    self.validator.locate_free_text(
                        parsed, page=claim.page, section=claim.section, evidence=claim.evidence,
                        origin=origin, evidence_url=None,
                    )
                    if value is not None else None
                )
            except ValidationError:
                # e.g. a page number the evidence schema rejects: drop this one
                # claim, never the whole paper's extraction.
                evidence = None
            # A correctly-located quote only proves the TEXT is real and on
            # the cited page - unlike the deterministic path, where a regex's
            # captured group physically IS the value, the LLM's `value` is
            # free-form JSON it wrote independently of the quote. Require the
            # same value-vs-evidence token overlap the deterministic path
            # enforces, so a real quote can't be paired with a fabricated or
            # exaggerated value.
            if evidence is None or not self.validator.supports_normalization(value, [evidence]):
                rejected.add(claim.path)
                continue
            # Token overlap alone is too coarse for numbers: "0.5" and "0.2"
            # share the token "0" and would otherwise pass. A numeric claim's
            # literal written form must appear in the quote, not just overlap
            # with it.
            if expected_type in (int, float) and str(value) not in normalize_text(evidence.evidence or ""):
                rejected.add(claim.path)
                continue
            try:
                set_extracted_field(
                    record, claim.path, value, [evidence], claim.path.startswith("limitations."),
                )
            except ValidationError:
                rejected.add(claim.path)
                continue
            accepted.add(claim.path)

        pending_paths = {path for path, _ in pending}
        errored = pending_paths - accepted - rejected
        for path in (rejected | errored) - accepted:
            mark_extraction_error(record, path, path.startswith("limitations."))
        return SemanticExtractionResult(sorted(accepted), sorted(rejected - accepted), sorted(errored))
