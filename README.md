# Ocean Research Hub

A collaborative scientific knowledge base for Oceanography × Statistics × Machine Learning × Deep Learning × Data Assimilation × Scientific ML.

## Goal

Turn scientific papers into deeply structured, evidence-backed records that researchers can search, compare, audit, and use to identify research gaps.

Core principles:

- **Scientific traceability first**: every extracted fact must point back to evidence in the source paper.
- **Never guess missing technical details**: use `NOT_REPORTED` when the paper does not state a value.
- **Separate facts from interpretation**: author-reported facts and limitations must remain distinct from AI/team analysis.
- **Multi-agent quality control**: implementation, QA, and scientific audit are independent responsibilities.

The detailed agent contract lives in `AGENTS.md`.

## Codex multi-agent setup

Project-level Codex configuration lives in `.codex/config.toml` with three specialist roles:

- **Developer** — `gpt-5.6-sol`, medium reasoning;
- **QA Engineer** — `gpt-5.6-terra`, high reasoning;
- **Scientific Auditor** — `gpt-5.6-sol`, high reasoning.

The parent/orchestrator is configured for `gpt-5.6-sol` with high reasoning.

Start Codex from the repository root:

```bash
codex
```

Then begin with:

```text
Read AGENTS.md carefully and start GitHub issue #1.
Use the Developer -> QA Engineer -> Scientific Auditor workflow.
Verify the effective subagent model/effort if the runtime exposes that metadata.
Do not move to issue #2 until issue #1 satisfies all acceptance criteria.
```

If the runtime ignores a role-specific model pin, report it explicitly rather than assuming model separation worked.
