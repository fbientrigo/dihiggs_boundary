#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

SMOKE_CSV="${DHB_ROOT}/configs/smoke_points.csv"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Checking smoke input: ${SMOKE_CSV}"

test -f "${SMOKE_CSV}" || fail "Missing smoke CSV: ${SMOKE_CSV}"

header="$(head -n 1 "${SMOKE_CSV}")"
expected_header="point_id,mH,mA,tan_beta,lambda6,M"

if [[ "${header}" != "${expected_header}" ]]; then
  echo "[DHB][DEBUG] found header:    ${header}" >&2
  echo "[DHB][DEBUG] expected header: ${expected_header}" >&2
  fail "Unexpected smoke CSV header"
fi

data_rows="$(tail -n +2 "${SMOKE_CSV}" | sed '/^[[:space:]]*$/d' | wc -l)"

if [[ "${data_rows}" -ne 3 ]]; then
  fail "Expected exactly 3 data rows, got ${data_rows}"
fi

awk -F',' '
NR == 1 { next }
NF != 6 {
  printf("[DHB][FAIL] Row %d has %d fields, expected 6\n", NR, NF) > "/dev/stderr"
  exit 1
}
$1 == "" {
  printf("[DHB][FAIL] Row %d has empty point_id\n", NR) > "/dev/stderr"
  exit 1
}
{
  for (i = 2; i <= 6; ++i) {
    if ($i == "") {
      printf("[DHB][FAIL] Row %d has empty numeric field %d\n", NR, i) > "/dev/stderr"
      exit 1
    }
    if ($i !~ /^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?$/) {
      printf("[DHB][FAIL] Row %d field %d is not numeric: %s\n", NR, i, $i) > "/dev/stderr"
      exit 1
    }
  }
}
' "${SMOKE_CSV}"

echo "[DHB] Smoke input check passed: ${data_rows} rows."
