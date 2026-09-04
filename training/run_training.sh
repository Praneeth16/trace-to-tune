#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv run "$script_dir/train.py" \
  --catalog "${TRACE_TO_TUNE_CATALOG:-serverless_lakebase_praneeth_catalog}" \
  --schema "${TRACE_TO_TUNE_SCHEMA:-trace_to_tune}" \
  --registered-model "${TRACE_TO_TUNE_MODEL:-serverless_lakebase_praneeth_catalog.trace_to_tune.skill_router}" \
  --max-steps "${TRACE_TO_TUNE_MAX_STEPS:-40}"
