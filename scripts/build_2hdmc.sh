#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

mkdir -p "${DHB_BUILD_ROOT}/logs"
mkdir -p "${DHB_2HDMC_ROOT}/lib"

echo "[DHB] Checking toolchain..."
command -v g++ >/dev/null
command -v make >/dev/null
command -v gsl-config >/dev/null

echo "[DHB] g++: $(g++ --version | head -n 1)"
echo "[DHB] make: $(make --version | head -n 1)"
echo "[DHB] gsl: $(gsl-config --version)"

echo "[DHB] Building 2HDMC..."
cd "${DHB_2HDMC_ROOT}"

make clean 2>&1 | tee "${DHB_BUILD_ROOT}/logs/2hdmc_clean.log"
make lib  2>&1 | tee "${DHB_BUILD_ROOT}/logs/2hdmc_make_lib.log"

test -f "${DHB_2HDMC_LIB}"

echo "[DHB] OK: ${DHB_2HDMC_LIB}"
