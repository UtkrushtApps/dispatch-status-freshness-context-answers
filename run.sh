#!/usr/bin/env bash
set -euo pipefail
cd /root/task

echo "[run] installing dependencies..."
pip install -q -r requirements.txt

if [ -f .env ]; then
  echo "[run] .env present (not required for selfcheck)"
fi

echo "[run] running selfcheck..."
python -m agent --selfcheck

echo "[run] collecting invariant tests (failures expected on starter)..."
set +e
python -m pytest -q invariants --collect-only >/dev/null 2>&1
collect_rc=$?
set -e
if [ "$collect_rc" -ne 0 ]; then
  echo "[run] test collection failed (rc=$collect_rc)"
  exit 1
fi

set +e
python -m pytest -q invariants >/dev/null 2>&1
test_rc=$?
set -e
if [ "$test_rc" -ne 0 ] && [ "$test_rc" -ne 1 ]; then
  echo "[run] pytest readiness failure (rc=$test_rc)"
  exit 1
fi

echo "ready"
