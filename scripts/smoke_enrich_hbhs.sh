#!/usr/bin/env bash
# End-to-end smoke of the HB/HS enrichment stage:
# evaluate_point on known pass/fail points -> dhb.enrich -> output checks.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

INPUT="${DHB_ROOT}/configs/smoke_points_hbhs.csv"
OUT_DIR="${DHB_RUNS_ROOT}/smoke"
THEORY_OUTPUT="${OUT_DIR}/evaluate_point_hbhs_smoke.csv"
ENRICHED_OUTPUT="${OUT_DIR}/hbhs_enriched_smoke.csv"
BIN="${DHB_BUILD_ROOT}/bin/evaluate_point"

PYTHON="${DHB_BUILD_ROOT}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Running hbhs enrichment smoke..."

"${PYTHON}" -c "import Higgs" 2>/dev/null \
  || fail "Higgs module not importable; run scripts/build_higgstools.sh"
"${PYTHON}" -c "import dhb" 2>/dev/null \
  || fail "dhb package not importable; pip install -e python/"

"${DHB_ROOT}/scripts/build_evaluate_point.sh"

mkdir -p "${OUT_DIR}"
rm -f "${THEORY_OUTPUT}" "${THEORY_OUTPUT}.tmp" \
      "${ENRICHED_OUTPUT}" "${ENRICHED_OUTPUT}.tmp"

"${BIN}" "${INPUT}" "${THEORY_OUTPUT}"
"${DHB_ROOT}/scripts/check_evaluate_point_output.sh" "${THEORY_OUTPUT}"

theory_ok_rows="$(awk -F',' '
NR == 1 { for (i = 1; i <= NF; ++i) col[$i] = i; next }
$(col["theory_ok"]) == "1" { n += 1 }
END { print n + 0 }' "${THEORY_OUTPUT}")"
if [[ "${theory_ok_rows}" -lt 1 ]]; then
  fail "Smoke input produced no theory_ok points; cannot exercise HB/HS"
fi

"${PYTHON}" -m dhb.enrich \
  --input "${THEORY_OUTPUT}" \
  --output "${ENRICHED_OUTPUT}" \
  --config "${DHB_ROOT}/configs/theory_atlas_v0.yaml"

test -f "${ENRICHED_OUTPUT}" || fail "Missing enriched output"
test -f "${OUT_DIR}/hbhs_manifest.json" || fail "Missing hbhs_manifest.json"

header="$(head -n 1 "${ENRICHED_OUTPUT}")"
for col in hb_allowed hb_max_obsratio hs_chi2 hs_delta_chi2 exp_ok enrich_status
do
  echo "${header}" | tr ',' '\n' | grep -qx "${col}" || fail "Missing enriched column: ${col}"
done

awk -F',' '
NR == 1 { for (i = 1; i <= NF; ++i) col[$i] = i; next }
{
  if (NF != length(col)) {
    printf("[DHB][FAIL] Row %d has %d fields, expected %d\n", NR, NF, length(col)) > "/dev/stderr"
    exit 1
  }
  status = $(col["enrich_status"])
  if ($(col["theory_ok"]) == "1") {
    if (status != "ok") {
      printf("[DHB][FAIL] theory_ok row %s has enrich_status=%s\n", $(col["point_id"]), status) > "/dev/stderr"
      exit 1
    }
    if ($(col["hb_allowed"]) != "0" && $(col["hb_allowed"]) != "1") {
      printf("[DHB][FAIL] Row %s invalid hb_allowed=%s\n", $(col["point_id"]), $(col["hb_allowed"])) > "/dev/stderr"
      exit 1
    }
    if ($(col["hs_chi2"]) == "nan" || $(col["hs_chi2"]) == "") {
      printf("[DHB][FAIL] Row %s has no hs_chi2\n", $(col["point_id"])) > "/dev/stderr"
      exit 1
    }
    enriched += 1
  } else {
    if (status != "skipped_theory_fail") {
      printf("[DHB][FAIL] theory-fail row %s has enrich_status=%s\n", $(col["point_id"]), status) > "/dev/stderr"
      exit 1
    }
    skipped += 1
  }
}
END {
  if (enriched < 1 || skipped < 1) {
    printf("[DHB][FAIL] Expected both enriched and skipped rows (got %d/%d)\n", enriched, skipped) > "/dev/stderr"
    exit 1
  }
  printf("[DHB] enriched=%d skipped=%d\n", enriched, skipped)
}' "${ENRICHED_OUTPUT}"

echo "[DHB] Output: ${ENRICHED_OUTPUT}"
echo "[DHB] hbhs enrichment smoke passed."
