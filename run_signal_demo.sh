#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m signal_demo.pipeline
python -m pytest -q tests_signal
python -m signal_demo.pipeline --verify-only
echo "SIGNAL_ENGINEERING_STATUS=PASS"
