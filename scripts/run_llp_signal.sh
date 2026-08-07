#!/usr/bin/env bash
# Attach a versioned LLP response to hbhs_enriched.csv.
#
# Usage:
#   scripts/run_llp_signal.sh <run_dir|hbhs_enriched.csv> <calibration.yaml>
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

TARGET="${1:-}"
CALIBRATION="${2:-}"
[[ -n "${TARGET}" && -n "${CALIBRATION}" ]] \
  || fail "Usage: $0 <run_dir|hbhs_enriched.csv> <calibration.yaml>"
[[ -f "${CALIBRATION}" ]] || fail "Calibration not found: ${CALIBRATION}"

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
OUTPUT="${OUT_DIR}/llp_signal_enriched.csv"

PYTHON="${DHB_BUILD_ROOT}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi
"${PYTHON}" -c "import dhb" 2>/dev/null \
  || fail "dhb package not importable; pip install -e python/"

# dhb.llp_signal deliberately returns non-zero for an invalid calibration, but
# still writes failure-marked rows and a manifest. Preserve that exit status.
echo "[DHB] Applying LLP response: ${CALIBRATION}"
set +e
"${PYTHON}" -m dhb.llp_signal \
  --input "${INPUT}" \
  --output "${OUTPUT}" \
  --calibration "${CALIBRATION}"
RC=$?
set -e

test -f "${OUTPUT}" || fail "Missing llp_signal_enriched.csv"
test -f "${OUT_DIR}/llp_signal_manifest.json" || fail "Missing llp_signal_manifest.json"

echo "[DHB] output: ${OUTPUT}"
echo "[DHB] manifest: ${OUT_DIR}/llp_signal_manifest.json"
exit "${RC}"
