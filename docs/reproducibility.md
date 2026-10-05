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
in the manifest; the reference embeds the full policy. The manifest records
provenance and does not enforce the current working tree's source hashes.

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
| `manifest.json` / `run_receipt.json` | Recorded provenance / output hashes |

Repeated runs with the pinned environment produce identical data CSV/JSON files
and reference/score values. DuckDB physical bytes are not promised deterministic;
each run records its own database hash. The receipt is published after all staged
artifacts, so interrupted publication fails verification. A failure before
publication preserves the last completed run. A per-output process lock rejects
simultaneous writers and releases on exit; its remaining file is harmless.

The GitHub workflow runs both pipelines and a Docker build/execution. Configuration
alone is not evidence of a passing hosted job; inspect the actual run status.
