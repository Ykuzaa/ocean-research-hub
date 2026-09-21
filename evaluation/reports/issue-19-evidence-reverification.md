# Independent evidence re-verification

Every asserted claim in the extraction artifact was re-checked against a
freshly parsed copy of the pinned PDF. This tool imports no extraction
rule and no provider: it only asks whether the stored snippet is really
on the page the artifact cites.

| Paper | Recorded SHA-256 reproduced | Asserted evidence records | Located | Not located | Page missing | No evidence |
|---|---|---:|---:|---:|---:|---:|
| `4dvarnet-ssh-2023` | yes | 20 | 20 | 0 | 0 | 0 |
| `oceannet-2023` | yes | 17 | 17 | 0 | 0 | 0 |
| `glonet-2025` | yes | 15 | 15 | 0 | 0 | 0 |
| `dincae-2-2022` | yes | 21 | 21 | 0 | 0 | 0 |

## Evidence records that did not re-verify

None. Every asserted claim's snippet was relocated in its cited source.

A `LOCATED` result proves only that the quotation is real and correctly
cited. It does not certify that the normalized value is the scientifically
correct reading of that quotation; that remains the independent Scientific
Auditor's decision.
