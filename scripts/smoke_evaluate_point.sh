#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

INPUT="${DHB_ROOT}/configs/smoke_points.csv"
OUT_DIR="${DHB_RUNS_ROOT}/smoke"
OUTPUT="${OUT_DIR}/evaluate_point_smoke.csv"
LOG="${OUT_DIR}/evaluate_point_smoke.log"
BIN="${DHB_BUILD_ROOT}/bin/evaluate_point"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Running evaluate_point smoke..."

"${DHB_ROOT}/scripts/check_base_ready.sh"
"${DHB_ROOT}/scripts/check_smoke_input.sh"
"${DHB_ROOT}/scripts/build_evaluate_point.sh"

mkdir -p "${OUT_DIR}"

rm -f "${OUTPUT}" "${OUTPUT}.tmp" "${LOG}"

"${BIN}" "${INPUT}" "${OUTPUT}" 2>&1 | tee "${LOG}"

test -f "${OUTPUT}" || fail "Missing smoke output: ${OUTPUT}"

data_rows="$(tail -n +2 "${OUTPUT}" | sed '/^[[:space:]]*$/d' | wc -l)"
if [[ "${data_rows}" -ne 3 ]]; then
  fail "Expected exactly 3 output data rows, got ${data_rows}"
fi

header="$(head -n 1 "${OUTPUT}")"

for col in \
  point_id \
  set_param_phys_ok \
  positivity_ok \
  unitarity_ok \
  perturbativity_ok \
  stability_ok \
  triple_ok \
  theory_ok \
  lambda1 \
  total_width_H2 \
  br_gammagamma_H2 \
  ctau_mm_H2 \
  yukawa_assignment \
  scalar_z2_status \
  rejection_stage \
  rejection_reason
do
  echo "${header}" | tr ',' '\n' | grep -qx "${col}" || fail "Missing output column: ${col}"
done

"${DHB_ROOT}/scripts/check_evaluate_point_output.sh" "${OUTPUT}"

echo "[DHB] Smoke output rows: ${data_rows}"
echo "[DHB] Output: ${OUTPUT}"
echo "[DHB] Log: ${LOG}"
echo "[DHB] evaluate_point smoke passed."
