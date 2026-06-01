#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

SRC="${DHB_ROOT}/src/evaluate_point.cpp"
BIN_DIR="${DHB_BUILD_ROOT}/bin"
BIN="${BIN_DIR}/evaluate_point"
LOG="${DHB_BUILD_ROOT}/logs/evaluate_point_build.log"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Building evaluate_point..."

test -f "${SRC}" || fail "Missing source: ${SRC}"
test -f "${DHB_2HDMC_LIB}" || fail "Missing 2HDMC library: ${DHB_2HDMC_LIB}"

mkdir -p "${BIN_DIR}" "${DHB_BUILD_ROOT}/logs"

g++ -std=c++11 -Wall -Wextra -O2 \
  -I"${DHB_2HDMC_INCLUDE}" \
  "${SRC}" \
  "${DHB_2HDMC_LIB}" \
  $(gsl-config --libs) \
  -o "${BIN}" \
  2>&1 | tee "${LOG}"

test -x "${BIN}" || fail "Build did not produce executable: ${BIN}"

echo "[DHB] OK: ${BIN}"
