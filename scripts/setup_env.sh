#!/usr/bin/env bash
# Source this file:
#   source scripts/setup_env.sh

_DHB_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DHB_ROOT="$(cd "${_DHB_SCRIPT_DIR}/.." && pwd)"

# One patched 2HDMC for the workspace: the dihiggs submodule (DATA_FLOW N2).
export DHB_2HDMC_ROOT="${DHB_2HDMC_ROOT:-$(cd "${DHB_ROOT}/../dihiggs/2hdmc" 2>/dev/null && pwd)}"
export DHB_HIGGSTOOLS_ROOT="${DHB_ROOT}/lib/higgstools-v1.2"

export DHB_HB_DATASET_ROOT="${DHB_ROOT}/dataset/hbdataset-v1.7"
export DHB_HS_DATASET_ROOT="${DHB_ROOT}/dataset/hsdataset-v1.1"

export DHB_BUILD_ROOT="${DHB_ROOT}/build"
export DHB_RUNS_ROOT="${DHB_ROOT}/runs"

export DHB_2HDMC_INCLUDE="${DHB_2HDMC_ROOT}/src"
export DHB_2HDMC_LIB="${DHB_2HDMC_ROOT}/lib/lib2HDMC.a"

mkdir -p "${DHB_BUILD_ROOT}" "${DHB_RUNS_ROOT}"

echo "[DHB] DHB_ROOT=${DHB_ROOT}"
echo "[DHB] DHB_2HDMC_ROOT=${DHB_2HDMC_ROOT}"
echo "[DHB] DHB_BUILD_ROOT=${DHB_BUILD_ROOT}"
echo "[DHB] DHB_RUNS_ROOT=${DHB_RUNS_ROOT}"
