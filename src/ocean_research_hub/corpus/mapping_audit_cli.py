"""Validate or replay an independent, hash-bound field-mapping audit report."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from .repository import CorpusNotFoundError, CorpusRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON INDEPENDENT_MAPPING_AUDIT report")
    parser.add_argument(
        "--database", type=Path,
        default=Path(os.getenv("OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db")),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="validate source binding and SHA-256 without appending packet or decision",
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("mapping audit report must be a JSON object")
        stored = CorpusRepository(args.database).record_mapping_audit(payload, dry_run=args.dry_run)
    except (
        OSError, json.JSONDecodeError, ValueError, CorpusNotFoundError, sqlite3.Error,
    ) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.dry_run:
        status = "VALID_ALREADY_RECORDED" if stored["already_recorded"] else "VALID_NOT_RECORDED"
    else:
        status = "RECORDED" if stored["appended"] else "UNCHANGED"
    print(json.dumps({"status": status, "mapping_audit": stored}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
