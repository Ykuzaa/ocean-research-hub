"""Independent data-level QA of the PR #35 + PR #36 merge.

Run from a worktree holding the merged tree, with the three hash-pinned PDFs in
.data/golden-pdfs/ (see docs/corpus-import.md). Never point it at the live database:

    cp .data/ocean-research-hub.db <qa-dir>/live-copy.db
    uv run --extra dev python evaluation/qa/combined_merge_check.py <qa-dir> [<populated-db-copy>]

It checks migration 0003 on a populated B16 database, catalogue reads that must not
create or modify a database, a duplicate-free B16 reimport, preservation of the audit
events, audit-report replay with hash-pinned PDFs (and refusal of a tampered PDF), and a
fresh V1->B16 build. Exit status is non-zero if any check fails.
"""
import hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

QA = Path(sys.argv[1])
LIVE_COPY = Path(sys.argv[2]) if len(sys.argv) > 2 else QA / "live-copy.db"
B16 = "import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx"
REPORTS = ["evaluation/reports/oai-0001-b16-scientific-audit.json",
           "evaluation/reports/oai-0002-b16-scientific-audit.json"]
CHAIN = ["import_staging/Ocean_Research_Hub_COMPLET.xlsx",
         "import_staging/Ocean_Research_Intelligence_EXPANDED_V2.xlsx",
         "import_staging/Ocean_Research_Intelligence_ENRICHED.xlsx",
         "import_staging/Ocean_Research_Intelligence_ENRICHED_B08.xlsx",
         "import_staging/Ocean_Research_Intelligence_ENRICHED_B15.xlsx", B16]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def snapshot(db):
    """SHA-256 of every staging_corpus_* table's ordered content, plus counts."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' and name like 'staging_corpus_%' order by name"):
        rows = c.execute(f"select * from {t} order by 1,2").fetchall()
        out[t] = (len(rows), hashlib.sha256(repr(rows).encode()).hexdigest())
    c.close()
    return out


def count(db, sql):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return c.execute(sql).fetchone()[0]
    finally:
        c.close()


def cli(*args):
    p = subprocess.run(["uv", "run", "--extra", "dev", *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def report_counts(path):
    return json.loads(Path(path).read_text())


# 1. Migration 0003 on a populated B16 database (copy of the live DB) -------------
db = QA / "migrated.db"
shutil.copy(LIVE_COPY, db)
before = snapshot(db)
check("populated copy has 94 audit events", before["staging_corpus_audit_events"][0] == 94,
      str(before["staging_corpus_audit_events"][0]))
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
SqlitePaperRepository(db).initialize()  # the app's startup path, which applies migrations
versions = [r[0] for r in sqlite3.connect(db).execute("select version from schema_migrations order by 1")]
check("migrations 0001-0003 recorded", versions[-3:] == ["0001_paper_records", "0002_research_intelligence", "0003_staging_corpus"], str(versions))
after = snapshot(db)
check("0003 leaves every staging table byte-identical", before == after,
      "" if before == after else str({k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}))
SqlitePaperRepository(db).initialize()
check("re-running migrations is a no-op", snapshot(db) == after)
trig = count(db, "select count(*) from sqlite_master where type='trigger' and name like 'staging_corpus_audit_no_%'")
check("append-only audit triggers present after migration", trig == 2, str(trig))
try:
    sqlite3.connect(db).execute("delete from staging_corpus_audit_events")
    check("audit delete rejected", False)
except sqlite3.DatabaseError as e:
    check("audit delete rejected", True, str(e))

# 2. Catalogue read without database creation ------------------------------------
tmp = Path(tempfile.mkdtemp(dir=QA))
absent = tmp / "nested" / "absent.db"
from ocean_research_hub.corpus.repository import CorpusRepository
r = CorpusRepository(absent)
empty = (r.summary() if hasattr(r, "summary") else None)
check("CorpusRepository read on absent DB creates nothing", not absent.exists() and not absent.parent.exists(),
      f"exists={absent.exists()} parent={absent.parent.exists()}")
os.environ["OCEAN_HUB_DB_PATH"] = str(absent)
from fastapi.testclient import TestClient
from ocean_research_hub.api import create_app
client = TestClient(create_app())  # no lifespan context: pure catalogue read
codes = {p: client.get(p).status_code for p in ["/api/corpus", "/api/corpus/papers", "/api/corpus/claims",
                                                 "/api/corpus/research-gaps", "/api/corpus/audits",
                                                 "/api/corpus/field-mappings", "/api/corpus/import-runs"]}
check("API catalogue reads return 200 on absent DB", all(v == 200 for v in codes.values()), str(codes))
check("API catalogue reads create no database file", not absent.exists() and not absent.parent.exists())
# read on an existing populated DB must not modify it
pre = hashlib.sha256(db.read_bytes()).hexdigest()
os.environ["OCEAN_HUB_DB_PATH"] = str(db)
c2 = TestClient(create_app())
for p in ["/api/corpus", "/api/corpus/papers?limit=500", "/api/corpus/papers/OAI-0001", "/api/corpus/audits"]:
    c2.get(p)
check("API reads leave populated DB byte-identical", hashlib.sha256(db.read_bytes()).hexdigest() == pre)
body = c2.get("/api/corpus").json()
print("   /api/corpus summary keys:", sorted(body)[:12])

# 3. B16 reimport without duplicates, events preserved ---------------------------
dup_sql = {
    "papers": "select count(*) from staging_corpus_papers",
    "claims": "select count(*) from staging_corpus_claims",
    "markers": "select count(*) from staging_corpus_field_markers",
    "mappings": "select count(*) from staging_corpus_field_mappings",
    "events": "select count(*) from staging_corpus_audit_events",
    "doi_dupes": "select count(*) from (select doi_key from staging_corpus_papers where doi_key is not null group by doi_key having count(*)>1)",
}
pre_counts = {k: count(db, q) for k, q in dup_sql.items()}
rep = QA / "reimport.json"
code, out = cli("ocean-research-hub-import-corpus", B16, "--database", str(db), "--report-out", str(rep))
check("B16 reimport exits 0", code == 0, out[-400:] if code else "")
post_counts = {k: count(db, q) for k, q in dup_sql.items()}
check("B16 reimport: row counts unchanged (no duplicates)", pre_counts == post_counts, f"{pre_counts} -> {post_counts}")
if rep.exists():
    rj = json.loads(rep.read_text())
    counts = rj.get("counts", rj)
    created = {k: v.get("created") for k, v in counts.items() if isinstance(v, dict) and v.get("created")}
    updated = {k: v.get("updated") for k, v in counts.items() if isinstance(v, dict) and v.get("updated")}
    check("B16 reimport: zero created / updated", not created and not updated, f"created={created} updated={updated}")
check("94 audit events preserved after reimport", post_counts["events"] == 94, str(post_counts["events"]))
snap_after_reimport = snapshot(db)
for t in ["staging_corpus_audit_events", "staging_corpus_claims", "staging_corpus_field_markers", "staging_corpus_papers", "staging_corpus_field_mappings"]:
    check(f"reimport leaves {t} identical", snap_after_reimport[t] == after[t])

# 4. Replay audit reports with hash-pinned PDFs ----------------------------------
for rpt in REPORTS:
    code, out = cli("ocean-research-hub-audit-report", rpt, "--database", str(db))
    check(f"replay {Path(rpt).name} exits 0", code == 0, out.strip()[-300:])
ev = count(db, "select count(*) from staging_corpus_audit_events")
check("replay on populated DB is idempotent (94 events)", ev == 94, str(ev))
check("replay leaves audit table identical", snapshot(db)["staging_corpus_audit_events"] == after["staging_corpus_audit_events"])

# tampered PDF must be refused
bad = Path(".data/golden-pdfs/4dvarnet-ssh-2023.pdf")
orig = bad.read_bytes()
try:
    bad.write_bytes(orig + b"\n%tamper")
    code, out = cli("ocean-research-hub-audit-report", REPORTS[0], "--database", str(db))
    check("replay refused when PDF hash differs", code != 0 and count(db, "select count(*) from staging_corpus_audit_events") == 94, out.strip()[-200:])
finally:
    bad.write_bytes(orig)

# 5. Fresh combined-tree chain V1 -> B16, replay, reimport -----------------------
fresh = QA / "fresh.db"
if fresh.exists():
    fresh.unlink()
SqlitePaperRepository(fresh).initialize()  # migrations first, as a new install would
for wb in CHAIN:
    code, out = cli("ocean-research-hub-import-corpus", wb, "--database", str(fresh))
    check(f"fresh import {Path(wb).name}", code == 0, out[-300:] if code else "")
for rpt in REPORTS:
    code, out = cli("ocean-research-hub-audit-report", rpt, "--database", str(fresh))
    check(f"fresh replay {Path(rpt).name}", code == 0, out.strip()[-200:])
fe = count(fresh, "select count(*) from staging_corpus_audit_events")
fd = count(fresh, "select count(distinct target_id) from staging_corpus_audit_events")
print(f"   fresh DB: {fe} events over {fd} targets")
check("fresh DB reaches 68 distinct audited claims", fd == 68, str(fd))
fresh_snap = snapshot(fresh)
code, out = cli("ocean-research-hub-import-corpus", B16, "--database", str(fresh))
check("fresh B16 reimport no-op", code == 0 and snapshot(fresh)["staging_corpus_claims"] == fresh_snap["staging_corpus_claims"]
      and snapshot(fresh)["staging_corpus_audit_events"] == fresh_snap["staging_corpus_audit_events"])
for k in ["staging_corpus_papers", "staging_corpus_claims", "staging_corpus_field_markers"]:
    check(f"fresh vs live copy: {k} row count equal", fresh_snap[k][0] == after[k][0], f"{fresh_snap[k][0]} vs {after[k][0]}")
# Mapping versions depend on import history (the live DB imported B15 before maps were
# stored), so compare the version the API serves, not the total row count.
served = {}
for name, path in (("fresh", fresh), ("live-copy", db)):
    m = CorpusRepository(path).field_mappings()
    served[name] = (m["version"]["source_name"], len(m["mappings"]),
                    sum(x["review_status"] == "PENDING" for x in m["mappings"]))
check("served mapping version is B16 with 981 PENDING rules in both DBs",
      served["fresh"] == served["live-copy"] == ("Ocean_Research_Intelligence_ENRICHED_B16.xlsx", 981, 981), str(served))
check("no mapping rule VALIDATED", count(db, "select count(*) from staging_corpus_field_mappings where review_status='VALIDATED'") == 0
      and count(fresh, "select count(*) from staging_corpus_field_mappings where review_status='VALIDATED'") == 0)

# verification-state gate: no paper FULLY_VERIFIED
os.environ["OCEAN_HUB_DB_PATH"] = str(db)
papers = TestClient(create_app()).get("/api/corpus/papers?limit=500").json()
items = papers.get("papers") or papers.get("items") or []
states = {}
for p in items:
    s = p.get("verification_state") or (p.get("state") or {}).get("verification_state")
    states[s] = states.get(s, 0) + 1
check("no paper FULLY_VERIFIED", "FULLY_VERIFIED" not in states, str(states))

fails = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
Path(QA / "merge_qa_results.json").write_text(json.dumps(results, indent=1))
sys.exit(1 if fails else 0)
