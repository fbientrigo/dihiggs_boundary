#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

CSV_PATH="${1:-}"
MIN_ROWS="${2:-1}"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

if [[ -z "${CSV_PATH}" ]]; then
  fail "Usage: $0 input.csv [min_rows]"
fi

echo "[DHB] Checking point input CSV: ${CSV_PATH}"

test -f "${CSV_PATH}" || fail "Missing CSV: ${CSV_PATH}"

header="$(head -n 1 "${CSV_PATH}" | tr -d '\r')"
expected_header="point_id,mH,mA,tan_beta,lambda6,M"

if [[ "${header}" != "${expected_header}" ]]; then
  echo "[DHB][DEBUG] found header:    ${header}" >&2
  echo "[DHB][DEBUG] expected header: ${expected_header}" >&2
  fail "Unexpected input CSV header"
fi

data_rows="$(tail -n +2 "${CSV_PATH}" | sed '/^[[:space:]]*$/d' | wc -l)"

if [[ "${data_rows}" -lt "${MIN_ROWS}" ]]; then
  fail "Expected at least ${MIN_ROWS} data rows, got ${data_rows}"
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
' "${CSV_PATH}"

echo "[DHB] Point input CSV check passed: ${data_rows} rows."
