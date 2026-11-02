#!/usr/bin/env bash
# One target: build evaluate_point against dihiggs/2hdmc (building the lib only if absent)
# and verify the HB/HS datasets that autoresearch preflight also checks.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

[ -f "${DHB_2HDMC_LIB}" ] || "${DHB_ROOT}/scripts/build_2hdmc.sh"
"${DHB_ROOT}/scripts/build_evaluate_point.sh"

for d in "${HB_DATASET:-${DHB_HB_DATASET_ROOT}}" "${HS_DATASET:-${DHB_HS_DATASET_ROOT}}"; do
  test -d "$d" || { echo "[DHB][FAIL] dataset dir missing: $d" >&2; exit 1; }
done
echo "[DHB] OK: evaluator + datasets"
