#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

RUN_DIR="${DHB_RUNS_ROOT}/tiny_boundary"
INPUT="${RUN_DIR}/input_points.csv"
OUTPUT="${RUN_DIR}/evaluate_point.csv"
LOG="${RUN_DIR}/evaluate_point.log"
SUMMARY_DIR="${RUN_DIR}/summary"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Running tiny boundary MVP..."

"${DHB_ROOT}/scripts/check_base_ready.sh"
"${DHB_ROOT}/scripts/build_evaluate_point.sh"

mkdir -p "${RUN_DIR}" "${SUMMARY_DIR}"

python3 "${DHB_ROOT}/scripts/generate_tiny_boundary_grid.py" \
  --output "${INPUT}"

"${DHB_ROOT}/scripts/check_point_input_csv.sh" "${INPUT}" 288

rm -f "${OUTPUT}" "${OUTPUT}.tmp" "${LOG}"

"${DHB_BUILD_ROOT}/bin/evaluate_point" "${INPUT}" "${OUTPUT}" \
  2>&1 | tee "${LOG}"

"${DHB_ROOT}/scripts/check_evaluate_point_output.sh" "${OUTPUT}"

input_rows="$(tail -n +2 "${INPUT}" | sed '/^[[:space:]]*$/d' | wc -l)"
output_rows="$(tail -n +2 "${OUTPUT}" | sed '/^[[:space:]]*$/d' | wc -l)"

if [[ "${input_rows}" -ne "${output_rows}" ]]; then
  fail "Input/output row mismatch: input=${input_rows}, output=${output_rows}"
fi

python3 "${DHB_ROOT}/scripts/summarize_boundary_run.py" \
  --input "${OUTPUT}" \
  --outdir "${SUMMARY_DIR}"

{
  echo "git_commit=$(git rev-parse HEAD)"
  echo "git_status_short_begin"
  git status --short
  echo "git_status_short_end"
  echo "date_utc=$(date -u -Is)"
  echo "hostname=$(hostname)"
  echo "gpp_version=$(g++ --version | head -n 1)"
  echo "gsl_version=$(gsl-config --version)"
  echo "dhb_root=${DHB_ROOT}"
  echo "input_csv=${INPUT}"
  echo "output_csv=${OUTPUT}"
  echo "input_rows=${input_rows}"
  echo "output_rows=${output_rows}"
} > "${RUN_DIR}/run_manifest.txt"

echo "[DHB] Tiny boundary run passed."
echo "[DHB] Run dir: ${RUN_DIR}"
echo "[DHB] Output: ${OUTPUT}"
echo "[DHB] Summary: ${SUMMARY_DIR}/summary.md"
echo "[DHB] Manifest: ${RUN_DIR}/run_manifest.txt"
