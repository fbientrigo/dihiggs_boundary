#!/usr/bin/env bash
# Build the boundary_atlas derived layer from an hbhs_enriched.csv.
#
# Usage:
#   scripts/make_boundary_atlas.sh <run_dir|hbhs_enriched.csv> [config.yaml]
#
# <run_dir|hbhs_enriched.csv> may be either a directory containing
# hbhs_enriched.csv, or a direct path to the CSV itself.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

TARGET="${1:-}"
[[ -n "${TARGET}" ]] || fail "Usage: scripts/make_boundary_atlas.sh <run_dir|hbhs_enriched.csv> [config.yaml]"
CONFIG="${2:-${DHB_ROOT}/configs/boundary_atlas_v0.yaml}"

if [[ -d "${TARGET}" ]]; then
  INPUT="${TARGET}/hbhs_enriched.csv"
  OUT_DIR="${TARGET}"
elif [[ -f "${TARGET}" ]]; then
  INPUT="${TARGET}"
  OUT_DIR="$(cd "$(dirname "${TARGET}")" && pwd)"
else
  fail "Not found: ${TARGET}"
fi

test -f "${INPUT}" || fail "Missing hbhs_enriched.csv: ${INPUT}"

PYTHON="${DHB_BUILD_ROOT}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

"${PYTHON}" -c "import dhb" 2>/dev/null \
  || fail "dhb package not importable; pip install -e python/"

echo "[DHB] Building boundary_atlas from ${INPUT}..."

"${PYTHON}" -m dhb.atlas \
  --input "${INPUT}" \
  --output-dir "${OUT_DIR}" \
  --config "${CONFIG}"

test -f "${OUT_DIR}/boundary_atlas.csv" || fail "Missing boundary_atlas.csv"
test -f "${OUT_DIR}/boundary_atlas_summary.json" || fail "Missing boundary_atlas_summary.json"
test -f "${OUT_DIR}/boundary_atlas_manifest.json" || fail "Missing boundary_atlas_manifest.json"

echo "[DHB] output: ${OUT_DIR}/boundary_atlas.csv"
echo "[DHB] summary: ${OUT_DIR}/boundary_atlas_summary.json"
echo "[DHB] manifest: ${OUT_DIR}/boundary_atlas_manifest.json"
echo "[DHB] make_boundary_atlas completed."
