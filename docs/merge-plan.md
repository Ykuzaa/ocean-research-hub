# What is ready to merge, and in which order

Everything below is validated locally. None of it is pushed: this session's permission
classifier refused `git push` and `gh pr merge` under "merge without review". Run these
yourself, or grant the permission and ask for them to be run.

State: `main` is at `ec08e4c`; `feat/corpus-v2` has six commits on top of it and contains
every commit of PR #35.

```bash
# 1. PR #36 — edition-aware research model (#11) and staging migrations (#30).
#    Green on its own: 273 tests. Already marked ready for review.
gh pr merge 36 --merge

# 2. The corpus v2 line. It also carries PR #35's commits, so #35 closes as merged.
git push -u origin feat/corpus-v2
gh pr create --base main --head feat/corpus-v2 \
  --title "feat(corpus-v2): evidence-gated corpus, independent re-check, and the tool over it" \
  --body-file docs/pr-corpus-v2.md
gh pr merge --merge     # after review

# 3. Check the two lines together once more on the merge result.
uv run pytest -q        # expected: 464 passed
```

Validated before writing this:

- `uv run pytest -q` on `feat/corpus-v2`: **448 passed**.
- The same on PR #36's branch: **273 passed**.
- The trial merge of both (`integration` branch): **464 passed**, conflicts only in
  `README.md` and `src/ocean_research_hub/api.py`, both resolved automatically by git.
- `uv run python -m ocean_research_hub.corpus_v2.gate evaluation/gold_v2/*.json`:
  43/43 records ok, no locate failure, no support warning.
- Frontend: `npx tsc --noEmit` clean, `npx vitest run` 11 passed, production build ok, and
  every page checked in a real browser at 1280 px and 390 px with no horizontal overflow
  and no console error.

PR #35 (`claude/issue-13-import-b15`) needs no action of its own: its head commit is an
ancestor of `feat/corpus-v2`, so merging step 2 closes it as merged. It cannot be made
green on its own — the fix its tests need depends on a commit that came after it.
