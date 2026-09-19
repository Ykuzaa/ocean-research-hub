"""Curated corpus: the domain taxonomy and the user-provided seed paper list."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any


@cache
def load_seed() -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("seed.json").read_text(encoding="utf-8"))


def domain_ids() -> list[str]:
    return [domain["id"] for domain in load_seed()["domains"]]
