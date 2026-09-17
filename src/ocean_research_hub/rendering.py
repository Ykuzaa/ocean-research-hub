"""Minimal, dependency-free paper detail rendering for milestone one."""

from __future__ import annotations

import json
from html import escape

from pydantic import BaseModel

from ocean_research_hub.ingestion.models import StoredPaper
from ocean_research_hub.schemas.paper_record import EvidenceField, SourceEvidence


COMPARISON_SECTIONS = (
    ("data", "Data"),
    ("architecture", "Architecture"),
    ("training", "Training"),
    ("objective", "Losses"),
    ("evaluation", "Evaluation"),
    ("results", "Results"),
    ("limitations", "Limitations"),
)


def render_paper_detail(paper: StoredPaper) -> str:
    title = paper.record.paper.title.value or "Untitled paper"
    sections: list[str] = []
    for section_name in type(paper.record).model_fields:
        section = getattr(paper.record, section_name)
        sections.append(
            f"<section><h2>{escape(section_name.replace('_', ' ').title())}</h2>"
            f"{_render_model(section, section_name)}</section>"
        )

    warnings = "".join(f"<li>{escape(item)}</li>" for item in paper.warnings)
    warning_block = (
        f"<aside><h2>Ingestion warnings</h2><ul>{warnings}</ul></aside>"
        if warnings
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Ocean Research Hub</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 72rem; margin: 0 auto; padding: 2rem; line-height: 1.5; }}
    header, section, aside {{ margin-bottom: 1.25rem; padding: 1rem 1.25rem; border: 1px solid #7893; border-radius: .6rem; }}
    h1, h2, h3 {{ margin-top: 0; }}
    dl {{ display: grid; grid-template-columns: minmax(10rem, 1fr) 3fr; gap: .55rem 1rem; }}
    dt {{ font-weight: 650; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
    .status {{ font-size: .8rem; padding: .1rem .4rem; border: 1px solid currentColor; border-radius: 1rem; }}
    .evidence {{ display: block; opacity: .8; font-size: .9rem; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p>Workflow: <span class="status">{escape(paper.workflow_status.value)}</span></p>
    <p>Paper ID: <code>{escape(paper.id)}</code></p>
  </header>
  {warning_block}
  {"".join(sections)}
</body>
</html>"""


def render_paper_comparison(left: StoredPaper, right: StoredPaper) -> str:
    """Render an ordered, field-level comparison without changing audit state."""
    left_title = left.record.paper.title.value or "Untitled paper"
    right_title = right.record.paper.title.value or "Untitled paper"
    sections = "".join(
        _render_comparison_section(
            heading,
            section_name,
            getattr(left.record, section_name),
            getattr(right.record, section_name),
        )
        for section_name, heading in COMPARISON_SECTIONS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Compare papers · Ocean Research Hub</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 90rem; margin: 0 auto; padding: 2rem; line-height: 1.45; }}
    header, section, aside {{ margin-bottom: 1.25rem; padding: 1rem 1.25rem; border: 1px solid #7893; border-radius: .6rem; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: .7rem; border-top: 1px solid #7893; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
    thead th {{ border-top: 0; }}
    th:first-child {{ width: 19%; }}
    .status, .provenance {{ display: inline-block; margin-top: .35rem; margin-right: .25rem; font-size: .75rem; padding: .1rem .4rem; border: 1px solid currentColor; border-radius: 1rem; }}
    .not-reported {{ font-style: italic; opacity: .85; }}
    .ai-interpretation {{ border-left: .35rem solid #a855f7; padding-left: .65rem; background: #a855f712; }}
    details {{ margin-top: .45rem; font-size: .9rem; }}
    .evidence {{ display: block; margin-top: .35rem; padding-left: .6rem; border-left: .15rem solid #7898; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>Paper comparison</h1>
    <p>Every value retains its verification status and provenance. Missing values remain explicitly <strong>NOT_REPORTED</strong>.</p>
    <p><span class="provenance">AUTHOR_REPORTED_FACT / AUTHOR_REPORTED_LIMITATION</span> Author-reported content
       <span class="provenance ai-interpretation">AI_INTERPRETATION</span> AI interpretation</p>
  </header>
  <aside>
    <strong>Left:</strong> {escape(left_title)} <code>{escape(left.id)}</code>
    {_render_identity_audit(left.record.paper.title)}<br>
    <strong>Right:</strong> {escape(right_title)} <code>{escape(right.id)}</code>
    {_render_identity_audit(right.record.paper.title)}
  </aside>
  {sections}
</body>
</html>"""


def _render_comparison_section(
    heading: str,
    section_name: str,
    left: BaseModel,
    right: BaseModel,
) -> str:
    left_fields = dict(_flatten_evidence_fields(left))
    right_fields = dict(_flatten_evidence_fields(right))
    # Both objects have the same canonical schema. Keeping the model order also
    # makes output stable across calls and Python hash seeds.
    rows = []
    for relative_path, left_field in left_fields.items():
        right_field = right_fields[relative_path]
        label = " › ".join(part.replace("_", " ").title() for part in relative_path.split("."))
        full_path = f"{section_name}.{relative_path}"
        rows.append(
            f'<tr data-field="{escape(full_path)}"><th scope="row">{escape(label)}</th>'
            f"{_render_comparison_cell(left_field)}{_render_comparison_cell(right_field)}</tr>"
        )
    return (
        f'<section id="{escape(section_name)}"><h2>{escape(heading)}</h2>'
        '<table><thead><tr><th scope="col">Field</th><th scope="col">Left paper</th>'
        f'<th scope="col">Right paper</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>'
    )


def _flatten_evidence_fields(
    model: BaseModel, prefix: str = ""
) -> list[tuple[str, EvidenceField[object]]]:
    fields: list[tuple[str, EvidenceField[object]]] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, EvidenceField):
            fields.append((path, value))
        elif isinstance(value, BaseModel):
            fields.extend(_flatten_evidence_fields(value, path))
    return fields


def _render_comparison_cell(field: EvidenceField[object]) -> str:
    status = field.status.value
    provenance = field.provenance_type.value
    classes = ["comparison-value"]
    if status == "NOT_REPORTED":
        classes.append("not-reported")
    if provenance == "AI_INTERPRETATION":
        classes.append("ai-interpretation")

    value = _render_field_value(field)

    supplied_sources = [
        source for source in (field.source, *field.sources) if source.is_supplied
    ]
    evidence = ""
    if supplied_sources:
        evidence_items = "".join(_render_source(source) for source in supplied_sources)
        evidence = f"<details><summary>Inspect source evidence</summary>{evidence_items}</details>"
    return (
        f'<td class="{" ".join(classes)}" data-status="{escape(status)}" '
        f'data-provenance="{escape(provenance)}">{escape(value)}<br>'
        f'<span class="status">{escape(status)}</span>'
        f'<span class="provenance">{escape(provenance)}</span>{evidence}</td>'
    )


def _json_value(value: object) -> str:
    def serialize(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        return str(item)

    return json.dumps(value, default=serialize, ensure_ascii=False)


def _render_field_value(field: EvidenceField[object]) -> str:
    """Render audit states without conflating failure with reported absence."""
    status = field.status.value
    if status == "CONFLICT":
        return _json_value(field.conflict_values)
    if status == "NOT_REPORTED":
        return "NOT_REPORTED"
    if field.value is None:
        # The schema permits a null value for extraction failure. A parser
        # failure is not evidence that the source omitted the field.
        return "EXTRACTION_ERROR (no extracted value)"
    return _json_value(field.value)


def _render_identity_audit(field: EvidenceField[object]) -> str:
    status = field.status.value
    provenance = field.provenance_type.value
    sources = [source for source in (field.source, *field.sources) if source.is_supplied]
    evidence = ""
    if sources:
        evidence = (
            "<details><summary>Inspect title source evidence</summary>"
            + "".join(_render_source(source) for source in sources)
            + "</details>"
        )
    return (
        f'<span class="status">{escape(status)}</span>'
        f'<span class="provenance">{escape(provenance)}</span>{evidence}'
    )


def _render_source(source: SourceEvidence) -> str:
    # Sources arrive from the validated schema; keeping this helper separate
    # makes escaping of both evidence and location explicit.
    location = ", ".join(
        part
        for part in (
            source.origin.value if source.origin else None,
            source.section,
            f"page {source.page}" if source.page else None,
            source.locator,
        )
        if part
    )
    claimed_value = (
        f"<br><strong>Supports:</strong> {escape(_json_value(source.claimed_value))}"
        if source.claimed_value is not None
        else ""
    )
    return (
        f'<span class="evidence"><strong>{escape(location or "Unlocated source")}</strong>: '
        f'{escape(source.evidence or "No evidence text")}{claimed_value}</span>'
    )


def _render_model(model: BaseModel, path: str) -> str:
    rows: list[str] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        label = name.replace("_", " ").title()
        if isinstance(value, EvidenceField):
            rows.append(_render_evidence_field(label, value, f"{path}.{name}"))
        elif isinstance(value, BaseModel):
            rows.append(
                f"<dt>{escape(label)}</dt><dd>{_render_model(value, f'{path}.{name}')}</dd>"
            )
    return f"<dl>{''.join(rows)}</dl>"


def _render_evidence_field(label: str, field: EvidenceField[object], path: str) -> str:
    rendered_value = _render_field_value(field)

    sources = [field.source, *field.sources]
    evidence_parts = []
    for source in sources:
        if not source.is_supplied:
            continue
        location = ", ".join(
            part
            for part in (
                source.origin.value if source.origin else None,
                source.section,
                f"page {source.page}" if source.page else None,
                source.locator,
            )
            if part
        )
        evidence_parts.append(
            f'<span class="evidence">{escape(location or "Unlocated source")}: '
            f"{escape(source.evidence or 'No evidence text')}</span>"
        )
    evidence_html = "".join(evidence_parts)
    return (
        f'<dt>{escape(label)}</dt><dd data-field="{escape(path)}">'
        f'{escape(rendered_value)} <span class="status">{escape(field.status.value)}</span> '
        f"<small>{escape(field.provenance_type.value)}</small>{evidence_html}</dd>"
    )
