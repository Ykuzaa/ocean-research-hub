"""Append a validated scientific-audit event to the staging corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .repository import CorpusNotFoundError, CorpusRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path, help="JSON file containing one explicit audit event")
    parser.add_argument(
        "--database", type=Path,
        default=Path(os.getenv("OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db")),
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.event.read_text(encoding="utf-8"))
        stored = CorpusRepository(args.database).record_audit(payload)
    except (OSError, json.JSONDecodeError, ValueError, CorpusNotFoundError) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "APPENDED", "audit_event": stored}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
