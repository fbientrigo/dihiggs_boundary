#!/usr/bin/env bash
# Build boundary_atlas_v1 from llp_signal_enriched.csv.
#
# Usage:
#   scripts/make_boundary_atlas_v1.sh <run_dir|llp_signal_enriched.csv>
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

TARGET="${1:-}"
[[ -n "${TARGET}" ]] || fail "Usage: $0 <run_dir|llp_signal_enriched.csv>"

if [[ -d "${TARGET}" ]]; then
  INPUT="${TARGET}/llp_signal_enriched.csv"
  OUT_DIR="${TARGET}"
elif [[ -f "${TARGET}" ]]; then
  INPUT="${TARGET}"
  OUT_DIR="$(cd "$(dirname "${TARGET}")" && pwd)"
else
  fail "Not found: ${TARGET}"
fi

test -f "${INPUT}" || fail "Missing llp_signal_enriched.csv: ${INPUT}"

PYTHON="${DHB_BUILD_ROOT}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi
"${PYTHON}" -c "import dhb" 2>/dev/null \
  || fail "dhb package not importable; pip install -e python/"

echo "[DHB] Building boundary_atlas_v1 from ${INPUT}..."
"${PYTHON}" -m dhb.atlas_v1 \
  --input "${INPUT}" \
  --output-dir "${OUT_DIR}"

test -f "${OUT_DIR}/boundary_atlas_v1.csv" || fail "Missing boundary_atlas_v1.csv"
test -f "${OUT_DIR}/boundary_atlas_v1_summary.json" || fail "Missing boundary_atlas_v1_summary.json"
test -f "${OUT_DIR}/boundary_atlas_v1_manifest.json" || fail "Missing boundary_atlas_v1_manifest.json"

echo "[DHB] output: ${OUT_DIR}/boundary_atlas_v1.csv"
echo "[DHB] summary: ${OUT_DIR}/boundary_atlas_v1_summary.json"
echo "[DHB] manifest: ${OUT_DIR}/boundary_atlas_v1_manifest.json"
