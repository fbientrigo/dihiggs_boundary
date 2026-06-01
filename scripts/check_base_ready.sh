#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

echo "[DHB] Checking base repository readiness..."

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

check_file() {
  local path="$1"
  test -f "$path" || fail "Missing file: $path"
  echo "[DHB][OK] file: $path"
}

check_dir() {
  local path="$1"
  test -d "$path" || fail "Missing directory: $path"
  echo "[DHB][OK] dir: $path"
}

check_command() {
  local name="$1"
  command -v "$name" >/dev/null || fail "Missing command: $name"
  echo "[DHB][OK] command: $name -> $(command -v "$name")"
}

check_marker() {
  local path="$1"
  local marker="$2"
  grep -q "$marker" "$path" || fail "Missing marker in $path: $marker"
  echo "[DHB][OK] marker: $marker"
}

check_command g++
check_command make
check_command gsl-config

check_dir "$DHB_2HDMC_ROOT"
check_dir "$DHB_2HDMC_INCLUDE"
check_file "$DHB_2HDMC_LIB"

check_file "$DHB_2HDMC_INCLUDE/THDM.h"
check_file "$DHB_2HDMC_INCLUDE/SM.h"
check_file "$DHB_2HDMC_INCLUDE/Constraints.h"
check_file "$DHB_2HDMC_INCLUDE/DecayTable.h"

check_file "$DHB_ROOT/docs/evaluate_point_contract.md"

check_marker "$DHB_ROOT/docs/evaluate_point_contract.md" "hard-Z2-breaking"
check_marker "$DHB_ROOT/docs/evaluate_point_contract.md" "Required output columns"
check_marker "$DHB_ROOT/docs/evaluate_point_contract.md" "ctau_mm_H2"
check_marker "$DHB_ROOT/docs/evaluate_point_contract.md" "Initial smoke requirement"
check_marker "$DHB_ROOT/docs/evaluate_point_contract.md" "Every input point must produce exactly one output row"

bash -n "$DHB_ROOT/scripts/setup_env.sh"
bash -n "$DHB_ROOT/scripts/build_2hdmc.sh"
bash -n "$DHB_ROOT/scripts/build_2hdmc_link_smoke.sh"

echo "[DHB] Base readiness check passed."
