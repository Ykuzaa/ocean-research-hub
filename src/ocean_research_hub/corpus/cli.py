"""``ocean-research-hub-import-corpus``: import the issue #13 staging workbook."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .repository import CorpusRepository
from .workbook import WorkbookValidationError, read_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, help="base (9 worksheets) or supplement staging workbook (.xlsx)")
    parser.add_argument(
        "--database", type=Path,
        default=Path(os.getenv("OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db")),
        help="SQLite database shared with the API (default: $OCEAN_HUB_DB_PATH)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="run every check, including those against the stored corpus, report what would change; write nothing",
    )
    parser.add_argument(
        "--allow-revert", action="store_true",
        help="apply rows that return to an earlier stored version (refused by default); each is reported",
    )
    parser.add_argument(
        "--record-versions", action="store_true",
        help="do not import: record the row versions of this already-imported workbook, so the "
             "stale-import guard covers a database built before versions were kept",
    )
    parser.add_argument("--report-out", type=Path, help="write the import report as JSON")
    args = parser.parse_args(argv)

    try:
        book = read_workbook(args.workbook)
    except WorkbookValidationError as exc:
        print(json.dumps({"status": "REJECTED", "errors": exc.errors}, indent=2), file=sys.stderr)
        return 2

    try:
        if args.record_versions:
            added = CorpusRepository(args.database).record_versions(book)
            print(json.dumps({"status": "VERSIONS_RECORDED", "workbook_sha256": book.sha256, "versions_added": added}, indent=2))
            return 0
        if args.dry_run:
            # Check against a throwaway copy, so not even the schema is written.
            with tempfile.TemporaryDirectory() as scratch:
                database = Path(scratch) / "dry-run.db"
                if args.database.exists():
                    shutil.copyfile(args.database, database)
                report = CorpusRepository(database).import_workbook(book, dry_run=True, allow_revert=args.allow_revert)
        else:
            report = CorpusRepository(args.database).import_workbook(book, allow_revert=args.allow_revert)
    except WorkbookValidationError as exc:
        print(json.dumps({"status": "REJECTED", "errors": exc.errors}, indent=2), file=sys.stderr)
        return 2
    result = {"status": "VALID_NOT_IMPORTED" if args.dry_run else "IMPORTED", **report.as_dict()}
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
