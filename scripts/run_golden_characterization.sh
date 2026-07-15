#!/usr/bin/env bash
set -euo pipefail

# CI / local entry point for the evaluate_point golden characterization suite:
# clean-build the vendored stock 2HDMC, build the evaluate_point binary, then
# run the golden tests with the binary REQUIRED (absence fails, not skips).
#
# See docs/characterization_evaluate_point.md. Total runtime is dominated by
# the ~10 s 2HDMC build; the golden input is 6 points.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

bash scripts/build_2hdmc.sh
bash scripts/build_evaluate_point.sh

DHB_REQUIRE_EVALUATE_POINT=1 python3 -m pytest -v tests/test_golden_evaluate_point.py
