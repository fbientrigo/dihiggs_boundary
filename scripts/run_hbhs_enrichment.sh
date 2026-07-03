#!/usr/bin/env bash
# Run the HB/HS enrichment stage on a run directory or campaign directory.
#
# Usage:
#   scripts/run_hbhs_enrichment.sh <run_dir | campaign_dir | evaluate_point.csv>
#
# Accepts:
#   - a run directory containing evaluate_point.csv
#   - a campaign directory containing index/all_evaluate_point.csv
#   - a direct path to an evaluate_point-format CSV
# Writes hbhs_enriched.csv + hbhs_manifest.json next to the input CSV.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

TARGET="${1:-}"
[[ -n "${TARGET}" ]] || fail "Usage: $0 <run_dir | campaign_dir | evaluate_point.csv>"

if [[ -f "${TARGET}" ]]; then
  INPUT="${TARGET}"
elif [[ -f "${TARGET}/evaluate_point.csv" ]]; then
  INPUT="${TARGET}/evaluate_point.csv"
elif [[ -f "${TARGET}/index/all_evaluate_point.csv" ]]; then
  INPUT="${TARGET}/index/all_evaluate_point.csv"
else
  fail "No evaluate_point.csv or index/all_evaluate_point.csv under: ${TARGET}"
fi

OUTPUT="$(dirname "${INPUT}")/hbhs_enriched.csv"

PYTHON="${DHB_BUILD_ROOT}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi
"${PYTHON}" -c "import Higgs" 2>/dev/null \
  || fail "Higgs module not importable; run scripts/build_higgstools.sh"
"${PYTHON}" -c "import dhb" 2>/dev/null \
  || fail "dhb package not importable; pip install -e python/"

echo "[DHB] Enriching: ${INPUT}"
"${PYTHON}" -m dhb.enrich \
  --input "${INPUT}" \
  --output "${OUTPUT}" \
  --config "${DHB_ROOT}/configs/theory_atlas_v0.yaml"

echo "[DHB] hbhs enrichment done: ${OUTPUT}"
