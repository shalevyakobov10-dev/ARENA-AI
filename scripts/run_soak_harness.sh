#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

CYCLES="${1:-250}"
if ! [[ "$CYCLES" =~ ^[1-9][0-9]*$ ]]; then
  echo "Usage: $0 [positive_cycle_count]" >&2
  exit 2
fi
if (( CYCLES > 20000 )); then
  echo "Cycle count must not exceed 20000" >&2
  exit 2
fi

export PMMB_SOAK_CYCLES="$CYCLES"
export PMMB_SOAK_LOAD_WORKERS="${PMMB_SOAK_LOAD_WORKERS:-2}"
python -m pytest -q tests/test_soak_harness.py
