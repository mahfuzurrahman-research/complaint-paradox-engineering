# Reproducibility

## Local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
bash run_public_demo.sh
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
