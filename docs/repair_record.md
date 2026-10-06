# Complaint Paradox engineering repair — 2026-10-06

Scope: the public `complaint-paradox-engineering` companion. Private scientific
code, empirical data, manuscripts and CV files are outside this repair.

## Why the previous workflow was red

Baseline commit `26b9e51d39a1e7a2700cfe3b3378685eebd7b29e` had a failed workflow
summary for run `37372191880`. Its only job, `111971836260`, was cancelled with
`runner_id=0`, no runner name and no executed steps. There was no executed test or
Docker failure in that attempt. Rerunning the job on unchanged code completed
successfully in attempt 2, including Docker and artifact upload. This identifies
an unstarted/cancelled job; the API evidence does not establish the underlying
runner-scheduling cause.

## Engineering defects corrected

| Defect | Consequence | Repair and regression evidence |
|---|---|---|
| Review queue checked only for duplicates/actions | Removing all seven required alerts in a small reproduction still returned PASS | SQL reconstructs the complete expected queue; omission, addition, duplicate, rank, metadata and residual corruption fail |
| Point flags and CUSUM state trusted from Python | Incorrect alerts, accumulation or directions could escape numerical checks | Independent point decisions and recursive SQL CUSUM, including latch/recovery/gap tests |
| Quality rows and reference quantities not fully reconstructed from raw records | Wrong admission/metadata or rehashed reference values could be accepted | Raw schedule/admission reconstruction, baseline rate/dispersion/exposure parity and lineage checks |
| Receipt verification relied on artifact hashes | Altered artifacts could pass when hashes were rewritten | Raw-input replay of CSV/JSON and all database relations; current manifest enforced |
| JSON/schema/type guards incomplete | Duplicate JSON keys, unsupported policy fields or invalid numeric types were ambiguous | Exact policy contract, strict JSON and bounded count validation |
| Original panel CSV errors not handled consistently | Duplicate headers/ragged rows could be accepted; nonnumeric cells could crash monitoring | Exact headers, row/identifier validation and structured FAIL reports |
| Original SQL allowed non-finite outcomes or blank/padded IDs | Data-quality PASS could disagree with Python monitoring | Explicit finite-value and identifier gates |
| Per-file publication could leave mixed runs on replacement failure | Earlier complete output could become unusable | Fully verified sibling stage, directory replacement and exception rollback |
| Lock inside replaceable output tied to the old directory | Whole-directory replacement requires a stable lock; path aliases can bypass inconsistent lock names | Canonical parent and sibling lock with alias/concurrency tests |
| Existing output ownership unguarded | A chosen output folder could contain unrelated files | Exact generated inventory required; unknown contents and symlinks preserved |
| Documentation described weaker verification and pending baseline CI | Readers could misunderstand the available evidence | Updated validation, reproducibility and capability records; live CI badge |

The detector thresholds, seed, baseline split and default scientific boundaries
are unchanged. The default reference remains `signal-v1-e5d10fd3709c3b5b`, with
60 queue rows and the previously reported detections and misses. Tests rose from
43 to 123; signal SQL gates rose from 10 to 26. These repairs validate the
engineering demonstration. They do not calibrate real-world false-alarm rates
or prove the scientific complaint paradox. Receipts remain unsigned; publication
rollback covers ordinary exceptions rather than hard-crash durability.

Floating-point SQL aggregates use explicit ordering, as described in the
[DuckDB aggregate documentation](https://duckdb.org/docs/current/sql/functions/aggregates),
so independently rebuilt database contents agree in the pinned environment.
