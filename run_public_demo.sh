#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p outputs
python src/monitoring/panel_monitor.py \
  --input data/synthetic/demo_panel.csv \
  --output outputs/monitor_summary.json

python sql/bootstrap_duckdb.py \
  --input data/synthetic/demo_panel.csv \
  --database outputs/public_demo.duckdb \
  --quality-output outputs/sql_quality.json

python src/reporting/build_report.py \
  --monitor outputs/monitor_summary.json \
  --quality outputs/sql_quality.json \
  --json-output outputs/public_report.json \
  --markdown-output outputs/public_report.md

python dashboards/build_demo_dashboard.py \
  --report outputs/public_report.json \
  --output outputs/public_dashboard.html

python examples/mini_panel_fe_demo.py data/synthetic/demo_panel.csv
python -m pytest -q tests

echo "PUBLIC_COMPANION_STATUS=PASS"
