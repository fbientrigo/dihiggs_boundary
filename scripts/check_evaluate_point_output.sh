#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

OUTPUT="${1:-${DHB_RUNS_ROOT}/smoke/evaluate_point_smoke.csv}"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Checking evaluate_point output: ${OUTPUT}"

test -f "${OUTPUT}" || fail "Missing output CSV: ${OUTPUT}"

header="$(head -n 1 "${OUTPUT}")"
data_rows="$(tail -n +2 "${OUTPUT}" | sed '/^[[:space:]]*$/d' | wc -l)"

if [[ "${data_rows}" -lt 1 ]]; then
  fail "Expected at least 1 data row, got ${data_rows}"
fi

required_columns=(
  point_id
  mh
  mH
  mA
  mHp
  tan_beta
  beta
  sin_ba
  lambda6_input
  lambda7_input
  M
  M2
  m12_sq_input
  M2_recomputed
  relative_M2_reconstruction_error
  set_param_phys_ok
  positivity_ok
  unitarity_ok
  perturbativity_ok
  stability_ok
  triple_ok
  theory_ok
  stu_ok
  physics_ok
  lambda1
  lambda2
  lambda3
  lambda4
  lambda5
  lambda6_derived
  lambda7_derived
  m12_sq_derived
  tan_beta_derived
  stu_S
  stu_T
  stu_U
  width_bb_H2
  width_tautau_H2
  width_WW_H2
  width_ZZ_H2
  width_gammagamma_H2
  width_Zgamma_H2
  width_gg_H2
  width_hh_H2
  total_width_H2
  br_gammagamma_H2
  ctau_mm_H2
  yukawa_assignment
  scalar_z2_status
  soft_z2_only
  rejection_stage
  rejection_reason
)

for col in "${required_columns[@]}"; do
  echo "${header}" | tr ',' '\n' | grep -qx "${col}" || fail "Missing output column: ${col}"
done

awk -F',' '
NR == 1 {
  for (i = 1; i <= NF; ++i) {
    col[$i] = i
  }
  next
}
{
  if (NF != length(col)) {
    printf("[DHB][FAIL] Row %d has %d fields, expected %d\n", NR, NF, length(col)) > "/dev/stderr"
    exit 1
  }

  if ($(col["point_id"]) == "") {
    printf("[DHB][FAIL] Row %d has empty point_id\n", NR) > "/dev/stderr"
    exit 1
  }

  for (name in col) {
    if ($(col[name]) == "") {
      printf("[DHB][FAIL] Row %d has empty column %s\n", NR, name) > "/dev/stderr"
      exit 1
    }
  }

  if ($(col["yukawa_assignment"]) != "type-I") {
    printf("[DHB][FAIL] Row %d has unexpected yukawa_assignment=%s\n", NR, $(col["yukawa_assignment"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["scalar_z2_status"]) != "hard_broken_lambda6") {
    printf("[DHB][FAIL] Row %d has unexpected scalar_z2_status=%s\n", NR, $(col["scalar_z2_status"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["soft_z2_only"]) != "0") {
    printf("[DHB][FAIL] Row %d has unexpected soft_z2_only=%s\n", NR, $(col["soft_z2_only"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["set_param_phys_ok"]) != "0" && $(col["set_param_phys_ok"]) != "1") {
    printf("[DHB][FAIL] Row %d invalid set_param_phys_ok=%s\n", NR, $(col["set_param_phys_ok"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["triple_ok"]) != "0" && $(col["triple_ok"]) != "1") {
    printf("[DHB][FAIL] Row %d invalid triple_ok=%s\n", NR, $(col["triple_ok"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["theory_ok"]) != "0" && $(col["theory_ok"]) != "1") {
    printf("[DHB][FAIL] Row %d invalid theory_ok=%s\n", NR, $(col["theory_ok"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["stu_ok"]) != "0" && $(col["stu_ok"]) != "1") {
    printf("[DHB][FAIL] Row %d invalid stu_ok=%s\n", NR, $(col["stu_ok"])) > "/dev/stderr"
    exit 1
  }

  if ($(col["physics_ok"]) != "0" && $(col["physics_ok"]) != "1") {
    printf("[DHB][FAIL] Row %d invalid physics_ok=%s\n", NR, $(col["physics_ok"])) > "/dev/stderr"
    exit 1
  }

  seen_rows += 1
}
END {
  if (seen_rows < 1) {
    printf("[DHB][FAIL] No data rows seen\n") > "/dev/stderr"
    exit 1
  }
}
' "${OUTPUT}"

echo "[DHB] evaluate_point output check passed: ${data_rows} rows."
