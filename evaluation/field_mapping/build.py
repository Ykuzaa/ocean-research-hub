"""Build the #29 mapping pre-review from the B16 database and proposals.py, with guards.

Usage: python evaluation/field_mapping/build.py <copy-of-b16-db> evaluation/field_mapping
Reads the database read-only. Output is AI_INTERPRETATION; nothing is VALIDATED or projected.
"""
import collections, csv, hashlib, json, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import proposals as P

db, out = sys.argv[1], Path(sys.argv[2])
verdict_file = out / "b16-field-path-map-auditor-verdicts.json"
verdicts = ({v["rule_id"]: v for v in json.loads(verdict_file.read_text())["verdicts"]}
            if verdict_file.exists() else {})
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
contract = {r[0] for r in c.execute("SELECT field_path FROM staging_corpus_field_contract")}
version = c.execute("SELECT version_id, workbook_sha256 FROM staging_corpus_mapping_versions "
                    "WHERE source_name='Ocean_Research_Intelligence_ENRICHED_B16.xlsx'").fetchone()
rules = c.execute("SELECT original_path, canonical_path, decision FROM staging_corpus_field_mappings "
                  "WHERE version_id=? ORDER BY original_path", (version[0],)).fetchall()
paths = {r[0] for r in rules}

unknown = (set(P.MAPPED) | set(P.UNMAPPED) | set(P.AMBIGUOUS_REASONS)) - paths
bad_targets = {p: t for p, t in P.MAPPED.items() if t not in contract}
overlap = set(P.MAPPED) & set(P.UNMAPPED)
assert not unknown, f"proposal paths not in B16 map: {sorted(unknown)}"
assert not bad_targets, f"targets outside the 162-field contract: {bad_targets}"
assert not overlap, overlap

BLOCKING_SCOPES = {"SEARCH_SPACE_NOT_SELECTED_CONFIGURATION", "CODE_CONFIG_NOT_LINKED_TO_PAPER_RESULT",
                   "HPO_COMPUTE_BUDGET", "CONFLICT_REVIEW", "EXTRACTION_METADATA", "APPLICABILITY_REVIEW"}
AI_TYPES = {"AI_INTERPRETATION"}
FACT_TYPES = {"AUTHOR_REPORTED_FACT"}


def is_review(scope):
    s = (scope or "").lower()
    return "review" in s and "reviewed_" not in s  # REVIEWED_* = a reviewed method, not a review paper


def guard(path, target, claims):
    types = {cl["claim_type"] for cl in claims}
    scopes = {cl["subject_scope"] for cl in claims}
    blocked = sorted(s for s in scopes if s in BLOCKING_SCOPES)
    if blocked:
        return f"Guard: claim scope {blocked} must not be projected into a configuration/value field (#29 item 3)."
    if target.startswith("interpretation."):
        if types - AI_TYPES:
            return f"Guard: interpretation target needs AI_INTERPRETATION claims, found {sorted(types)}."
        return None
    if types & AI_TYPES:
        return f"Guard: AI_INTERPRETATION claims cannot be projected into author-reported field {target}."
    if target.startswith("limitations.") and target != "limitations.future_work":
        if types != {"AUTHOR_REPORTED_LIMITATION"}:
            return f"Guard: {target} requires AUTHOR_REPORTED_LIMITATION claims, found {sorted(types)}."
        if any(is_review(s) for s in scopes):
            return "Guard: review-level limitation of the field, not of the paper's own method."
        return None
    if target == "limitations.future_work":
        if types - {"AUTHOR_REPORTED_FACT", "AUTHOR_REPORTED_FUTURE_WORK"}:
            return f"Guard: unexpected claim types {sorted(types)} for future work."
        return None
    if types - FACT_TYPES:
        return f"Guard: mixed or non-fact claim types {sorted(types)}."
    if target.startswith("results.") and any(is_review(s) for s in scopes):
        return "Guard: review-level statement, not the paper's own result."
    return None


# Limitations: every AUTHOR_REPORTED_LIMITATION path under limitations.* -> limitations.author_reported
mapped = dict(P.MAPPED)
for (p,) in [(r[0],) for r in rules]:
    if p.startswith("limitations.") and p not in contract and p not in mapped:
        mapped[p] = "limitations.author_reported"

rows, stats = [], collections.Counter()
for original, proposed, decision in rules:
    claims = [json.loads(r[0]) for r in c.execute(
        "SELECT row_json FROM staging_corpus_claims WHERE field_path=?", (original,))]
    base = {"original_path": original, "source_decision": decision, "source_canonical_path": proposed,
            "n_claims": len(claims), "n_papers": len({cl["paper_id"] for cl in claims}),
            "claim_types": sorted({cl["claim_type"] for cl in claims}),
            "claim_ids": [cl["claim_id"] for cl in claims]}
    if decision == "MAPPED":
        # Workbook-exact contract path: identity projection, no meaning change possible.
        assert proposed == original and original in contract
        rec = {"proposed_decision": "MAPPED", "proposed_canonical_path": original,
               "reason": "Identity: source path is already a contract field."}
    elif original in P.UNMAPPED:
        rec = {"proposed_decision": "UNMAPPED", "proposed_canonical_path": None, "reason": P.UNMAPPED[original]}
    elif original in mapped and not claims:
        rec = {"proposed_decision": "AMBIGUOUS", "proposed_canonical_path": None,
               "reason": "No claims under this path; nothing to assess."}
    elif original in mapped:
        g = guard(original, mapped[original], claims)
        if g:
            rec = {"proposed_decision": "AMBIGUOUS", "proposed_canonical_path": None,
                   "reason": g, "blocked_candidate": mapped[original]}
            stats["guard_blocked"] += 1
        else:
            rec = {"proposed_decision": "MAPPED", "proposed_canonical_path": mapped[original],
                   "reason": "Synonym or container field; original path kept as qualifier."}
    else:
        rec = {"proposed_decision": "AMBIGUOUS", "proposed_canonical_path": None,
               "reason": "No claims under this path; nothing to assess." if not claims
               else P.AMBIGUOUS_REASONS.get(original, P.DEFAULT_AMBIGUOUS)}
    v = verdicts.get(original)
    if v:
        rec["auditor_verdict"] = v["verdict"]
        rec["auditor_reason"] = v["reason"]
        rec["auditor_offending_claim_ids"] = v.get("offending_claim_ids") or []
        if v.get("alternative_target"):
            rec["auditor_alternative_target"] = v["alternative_target"]
        if v["verdict"].startswith("DISSENT") and rec["proposed_decision"] == "MAPPED":
            # Auditor dissent wins: the rule returns to pending for human decision.
            rec = {**rec, "proposed_decision": "AMBIGUOUS", "proposed_canonical_path": None,
                   "blocked_candidate": rec["proposed_canonical_path"],
                   "reason": "Independent Scientific Auditor dissent: " + v["reason"]}
            stats["auditor_dissent"] += 1
    rec.update({"provenance_type": "AI_INTERPRETATION", "review_status": "PENDING",
                "human_validation_required": True})
    stats[(decision, rec["proposed_decision"])] += 1
    rows.append({**base, **rec})

claims_mapped = sum(r["n_claims"] for r in rows if r["proposed_decision"] == "MAPPED" and r["source_decision"] != "MAPPED")
doc = {
    "kind": "FIELD_PATH_MAPPING_PREREVIEW",
    "issue": 29,
    "status": "PROPOSAL_PENDING_HUMAN_VALIDATION",
    "provenance_type": "AI_INTERPRETATION",
    "note": ("Pre-review proposals only. No rule is VALIDATED and no projection is applied; "
             "#29 requires human validation of every rule before projection."),
    "independent_audit": ("Scientific Auditor (independent AI subagent) reviewed every non-identity rule and every claim "
                          "under it against the stored claim text; no PDF access. AI_INTERPRETATION, not a validation.")
                         if verdicts else None,
    "source_mapping_version": version[0],
    "source_workbook_sha256": version[1],
    "proposals_sha256": hashlib.sha256(Path(P.__file__).read_bytes()).hexdigest(),
    "counts": {"rules": len(rows),
               "identity_mapped": sum(r["source_decision"] == "MAPPED" for r in rows),
               "proposed_mapped_new": sum(r["proposed_decision"] == "MAPPED" and r["source_decision"] != "MAPPED" for r in rows),
               "proposed_unmapped": sum(r["proposed_decision"] == "UNMAPPED" for r in rows),
               "proposed_ambiguous": sum(r["proposed_decision"] == "AMBIGUOUS" for r in rows),
               "guard_blocked": stats["guard_blocked"],
               "auditor_dissent_returned_to_pending": stats["auditor_dissent"],
               "auditor_concur_on_mapped": sum(r.get("auditor_verdict") == "CONCUR" and r["proposed_decision"] == "MAPPED" for r in rows),
               "claims_under_new_mapped_paths": claims_mapped},
    "rules": rows,
}
out.mkdir(parents=True, exist_ok=True)
(out / "b16-field-path-map-prereview.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
with open(out / "b16-field-path-map-prereview.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["original_path", "source_decision", "proposed_decision", "proposed_canonical_path",
                "n_claims", "n_papers", "claim_types", "reason", "auditor_verdict", "human_decision", "human_reviewer", "reviewed_at"])
    for r in rows:
        w.writerow([r["original_path"], r["source_decision"], r["proposed_decision"],
                    r["proposed_canonical_path"] or "", r["n_claims"], r["n_papers"],
                    ";".join(r["claim_types"]), r["reason"], r.get("auditor_verdict", ""), "", "", ""])
print(json.dumps(doc["counts"], indent=1))
for r in rows:
    if r.get("blocked_candidate"):
        print("BLOCKED", r["original_path"], "->", r["blocked_candidate"], "|", r["reason"][:110])
