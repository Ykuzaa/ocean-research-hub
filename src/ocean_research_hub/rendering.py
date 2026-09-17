"""Minimal, dependency-free paper detail rendering for milestone one."""

from __future__ import annotations

import json
from html import escape

from pydantic import BaseModel

from ocean_research_hub.ingestion.models import StoredPaper
from ocean_research_hub.schemas.paper_record import EvidenceField


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
    if field.status.value == "CONFLICT":
        rendered_value = json.dumps(
            field.conflict_values, default=str, ensure_ascii=False
        )
    elif field.value is None:
        rendered_value = "Not reported"
    else:
        rendered_value = json.dumps(field.value, default=str, ensure_ascii=False)

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
