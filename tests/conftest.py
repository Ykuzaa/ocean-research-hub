"""Test-suite hermeticity: never let a developer's local .env reach a live LLM.

`ocean_research_hub.api` auto-enables the Gemini semantic-extraction step
whenever GEMINI_API_KEY is present in the process environment (including one
loaded from a gitignored local .env), so that running the real server "just
works" once a key is configured. Tests must stay deterministic, offline, and
free regardless of what is in a contributor's local .env, so every test run
strips these variables before each test and restores them afterwards.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
