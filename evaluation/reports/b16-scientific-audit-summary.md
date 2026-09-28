# B16 independent scientific-audit summary

Audit date: 2026-09-28
Auditor: `scientific-auditor:/root/scientific_audit`
Scope: B16 staging claims for OAI-0001 and OAI-0002, plus triage of locally available primary sources. This is not a paper-completeness attestation.

## Corpus and source identity

- `Ocean_Research_Intelligence_ENRICHED_B16.xlsx`: SHA-256 `084ecf1c254b1044c4e3075b97e79dac9f5522b5821aa8cbb5b05b27c1f0238f`.
- B16 contains 1,936 `SCIENTIFIC_CLAIMS` worksheet rows: 1,867 value-bearing claim rows and 69 absence markers (55 `NOT_EXTRACTED`, 14 `NOT_REPORTED` candidates). A candidate marker is not an independently established absence.
- OAI-0001 published paper: `.data/golden-pdfs/4dvarnet-ssh-2023.pdf`, SHA-256 `bfad134ecdf1a4786ee4fdadc21746ab9e2106618513d8418a357cb39f9f0b88`, GMD 16 (2023), pp. 2119–2147, DOI `10.5194/gmd-16-2119-2023`.
- OAI-0002 paginated author manuscript: `.data/golden-pdfs/oceannet-2023.pdf`, arXiv `2310.00813v2` dated 2024-09-04, SHA-256 `be82ff557769aff04b119490d6a2ebb718887a1e3962355ab10cc9a7291802e9`. The published Scientific Reports HTML, DOI `10.1038/s41598-024-72145-0`, was inspected as the published edition and has no page numbering.
- OAI-0002 published supplement: `.data/golden-pdfs/oceannet-2023-supplement.pdf`, SHA-256 `c3e7f690fab8563d4bfb2728a594bc2adb8e4d42a50872a1e0c97e34f4d7adbf`. It was reviewed separately and was never substituted for the main article.
- The declared code archives for OAI-0001 and OAI-0002 were not inspected or executed. No code-based attestation is made.

## Decisions on the imported B16 claim sets

| Paper | B16 claims reviewed | Verified | Partially verified | Not verified | Extraction error | Paper conclusion |
|---|---:|---:|---:|---:|---:|---|
| OAI-0001 / 4DVarNet-SSH | 42 | 19 | 0 | 1 | 22 | `PARTIALLY_VERIFIED` |
| OAI-0002 / OceanNet | 26 | 20 | 2 | 1 | 3 | `PARTIALLY_VERIFIED` |
| Total | 68 | 39 | 2 | 2 | 25 | 0 fully verified papers |

The complete claim-level decisions, locators, evidence summaries, reviewed values, experiments, provenance, source editions and hashes are in:

- `evaluation/reports/oai-0001-b16-scientific-audit.json`
- `evaluation/reports/oai-0002-b16-scientific-audit.json`

Both reports pass the PR #35 audit replay validator in `--dry-run` mode against the local B16 database. They do not constitute a complete review of every required canonical field or every relevant code artifact.

The hash-pinned PDFs are currently local ignored assets rather than bundled release artifacts. A clean checkout therefore cannot replay these reports until it downloads the exact editions from each report's `download_url` and verifies the declared SHA-256. Failure to obtain or match a source must block replay; it must not trigger substitution with another edition.

### OAI-0001

All 42 imported claims were checked against the hash-pinned published paper. Nineteen imported records are supported as written. `ORI-0020` remains `NOT_VERIFIED` because its negative method classification is an AI interpretation rather than an author-reported fact. `ORI-0021` misclassifies the motivating sparse-observation problem as an author-reported method limitation. `ORI-0022` uses the invalid provenance value `AUTHOR_REPORTED_FUTURE_WORK` even though its scientific wording is supported.

The other twenty records, `B16-0001` through `B16-0020`, use `OAI-0001:B16_SOURCE_REVIEW` as `experiment_id`. That string identifies an extraction/review operation, not a scientific experiment. Their values may be supported, but the records cannot be verified as a value–experiment assertion and are therefore `EXTRACTION_ERROR`. This repeated defect should become a golden-dataset regression case for experiment assignment.

### OAI-0002

All 26 imported claims were checked against the published article and the hash-pinned paginated manuscript; the supplement was checked as a distinct source. `ORI-0032` and `ORI-0033` are only partially verified because bare values `4` and `64` omit the required qualifiers “Fourier layers” and “modes per Fourier layer”. `ORI-0044` remains an AI interpretation and is not an author-reported negative PINN classification.

`ORI-0029` combines five-day input averaging with distinct Gulf of Mexico and Gulf Stream forecast leads under one generic experiment. `ORI-0040` embeds an extraction note in the scientific value: the symbolic coefficient is explicit, but no numerical coefficient was found in the main paper or supplement, and the code was not inspected. `ORI-0048` uses the invalid provenance value `AUTHOR_REPORTED_FUTURE_WORK`. These three records are `EXTRACTION_ERROR`.

## PR #35 output revalidation

At commit `d3ce39738437c5e078145e3af88848b16c285c74`, the application/database summary agreed with the reports: 68 audited claims, with latest decisions of 39 `VERIFIED`, 2 `PARTIALLY_VERIFIED`, 2 `NOT_VERIFIED` and 25 `EXTRACTION_ERROR`; 0 fully verified papers and 2 partially verified papers. Extraction completeness remains a separate axis: 21 papers are labelled `READY_FOR_AUDIT`, not extraction-complete.

The first OAI-0002 replay stored the source-edition label `ARXIV_AUTHOR_MANUSCRIPT_V2_2023`; the inspected file is arXiv v2 dated 2024-09-04. After correction of the deterministic event identity, replaying the final report appended 26 new, separately versioned events rather than overwriting the historical events. A second replay appended zero events. The latest OAI-0002 records now carry the corrected arXiv v2 2024 edition and preserve the separate supplement hash. The ledger consequently contains 94 historical audit events for 68 audited claims, while the latest-decision counts remain 39 `VERIFIED`, 2 `PARTIALLY_VERIFIED`, 2 `NOT_VERIFIED` and 25 `EXTRACTION_ERROR`.

Multi-source checks such as `ORI-0040` retain the supplement hash and review scope in addition to the primary-paper edition. These source identities must remain separate in future replays; collapsing them to an undifferentiated primary source would lose provenance.

## Additional-paper triage

No additional paper can honestly be declared fully audited from the current assets and staging rows.

| Paper | Local source | Honest next state | Blocking reason for full-paper verification |
|---|---|---|---|
| OAI-0004 / DINCAE 2.0 | Published GMD PDF, SHA-256 `017757e5a2394713d7c18f9b68de0559d003c4843c63d3c84ecc16a5d05d9bf0` | Best next claim-set audit candidate | 23 legacy claims cover only 23 of 162 contract fields; 139 are unreviewed, the documented scope is `LEGACY_BATCH_ONLY`, and relevant supplement/code coverage is not established. |
| OAI-0003 / GLONET | arXiv v3 manuscript, SHA-256 `bc9627304aefb8c29b1eb069a3362996c1b240940e7f7411585987445ad7b76f` | Audit after edition/conflict resolution | The published DOI edition has not been compared, and the legacy Transformer description conflicts with the later FNO/CNN description. |
| OAI-0026 / XiHe | arXiv v4 manuscript, SHA-256 `a7d1c25ed007983fb496ab174dcedb0bb85180f9fb0967fe499bc455e2198114` | Extend the existing 17-field golden subset | The existing audit is only a subset and contains one unresolved conflict; hardware, exact training years and ablation coverage remain open. |

OAI-0005 and OAI-0064 have relatively rich workbook coverage but no locally retained, hash-pinned primary-source package suitable for an independent offline audit. The historical `DETAILED` label is not sufficient evidence of extraction completeness.

## Mapping and status risks

- `FIELD_PATH_MAP` has 981 rows; 892 are labelled as rule-based AI interpretation. It is a mapping proposal, not a scientifically validated correspondence to canonical fields.
- Broad category mapping can erase experiment, unit, version and field-level distinctions. Original paths and wording must remain visible, and ambiguous mappings must stay pending.
- `NOT_EXTRACTED` means no extraction was completed. `NOT_REPORTED` can only be promoted after a documented source review adequate for the field, not after an unsuccessful keyword search.
- A paper-level `VERIFIED` decision requires a documented field-by-field completeness review in addition to claim verification. No paper currently meets that gate.
