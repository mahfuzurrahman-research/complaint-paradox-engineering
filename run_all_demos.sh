#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash run_public_demo.sh
bash run_signal_demo.sh
