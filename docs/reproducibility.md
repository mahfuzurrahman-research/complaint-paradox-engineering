# Reproducibility

## Local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
bash run_all_demos.sh
```

## Docker

```bash
docker build -t complaint-paradox-engineering .
docker run --rm complaint-paradox-engineering
```

## Expected public outputs

```text
outputs/monitor_summary.json
outputs/sql_quality.json
outputs/public_report.json
outputs/public_report.md
outputs/public_dashboard.html
outputs/public_demo.duckdb
```

These outputs are generated exclusively from the synthetic fixture.

## Signal stream

`bash run_signal_demo.sh` runs the fabricated stream, its tests and receipt
verification. `python -m pytest -q tests tests_signal` runs the combined suite.
`python -m signal_demo.pipeline --output /tmp/complaint-signals` permits a separate
output location. `--verify-only` verifies an existing complete artifact inventory.

The fixed calendar, seed and policy are in `contracts/signal_contract.json`.
The first 56 days fit the reference; the next 112 days are monitored without
refitting. Input row order does not change the reference or scores. Changes to
future observations cannot alter earlier monitoring results. Actual NumPy,
DuckDB and pytest versions, source hashes and the baseline input hash are recorded
in the manifest; the reference embeds the full policy. Verification enforces the
current source hashes, installed dependency versions and exact policy. Regenerate
outputs after a source, dependency or policy change. Historical receipts must be
verified in their matching checkout and pinned environment.

| Signal artifact | Purpose |
|---|---|
| `synthetic_signal_records.csv` | Fabricated raw records, no injection labels |
| `synthetic_injection_truth.csv` | Labels for offline evaluation only |
| `quality_buckets.csv` | All scheduled buckets, admission and reasons |
| `reference.json` | Frozen channel rates, dispersion and policy |
| `signal_monitor.csv` | Expected counts, residuals and stateful alerts |
| `review_queue.csv` | Pending reviews with reasons and bounded actions |
| `evaluation.json` | Injection comparisons, detections and misses |
| `signal_quality.json` | Quality counts, SQL checks and replay result |
| `signal_monitor.duckdb` | Typed raw/reference/monitor tables and marts |
| `manifest.json` / `run_receipt.json` | Enforced current provenance / unsigned replay and integrity receipt |

Repeated runs with the pinned environment produce identical data CSV/JSON files
and reference/score values. DuckDB physical bytes are not promised deterministic;
each run records its own database hash. SQL floating aggregates use explicit input
ordering. Verification compares all database relation schemas and sorted contents
to an independent rebuild, rather than requiring identical physical file bytes.
It reconstructs quality, reference, scores, queue, evaluation and QA from the raw
CSV inputs. A modified artifact remains invalid even if its receipt hash is updated.
An unsigned receipt cannot prove who produced a coherent set of inputs and outputs.

All artifacts and the receipt are verified in a sibling staging directory before
publication. The previous output is renamed to a backup, then the complete staged
directory takes its place. Ordinary publication exceptions restore the backup;
unrecognized contents and symlinks are refused. The stable sibling POSIX lock
`.signals.signal-demo.lock` rejects simultaneous writers, including parent-path
aliases, and releases on process exit. A leftover lock file is harmless.

This is exception rollback, not a durable transaction: there is no `fsync`
protocol or recovery guarantee after hard termination between the two renames.
Readers do not acquire a snapshot lock and can fail verification during a
replacement. Retry verification after the writer finishes. The old in-directory
`.signal_demo.lock` is accepted as an optional legacy file in completed outputs.

The GitHub workflow runs both pipelines and a Docker build/execution. Configuration
alone is not evidence of a passing hosted job; inspect the actual run status.
