#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_env.sh"

RUN_DIR="${DHB_RUNS_ROOT}/tiny_boundary"
INPUT="${RUN_DIR}/evaluate_point.csv"
OUTDIR="${RUN_DIR}/inspection"
PLOTDIR="${RUN_DIR}/plots"

fail() {
  echo "[DHB][FAIL] $*" >&2
  exit 1
}

echo "[DHB] Inspecting tiny boundary run..."

test -f "${INPUT}" || fail "Missing tiny boundary output: ${INPUT}. Run scripts/run_tiny_boundary.sh first."

python3 "${DHB_ROOT}/scripts/inspect_boundary_coordinates.py" \
  --input "${INPUT}" \
  --outdir "${OUTDIR}"

if python3 - <<'PY'
try:
    import matplotlib  # noqa: F401
except Exception:
    raise SystemExit(1)
PY
then
  python3 "${DHB_ROOT}/scripts/plot_boundary_pairs.py" \
    --input "${INPUT}" \
    --outdir "${PLOTDIR}"
else
  echo "[DHB][WARN] matplotlib not available; skipping plots."
fi

echo "[DHB] Inspection artifacts:"
echo "[DHB] - ${OUTDIR}/theory_ok_points.csv"
echo "[DHB] - ${OUTDIR}/coordinate_acceptance.csv"
echo "[DHB] - ${OUTDIR}/rejection_by_coordinate.csv"
echo "[DHB] - ${OUTDIR}/pair_acceptance.csv"
echo "[DHB] - ${OUTDIR}/coordinate_summary.md"
echo "[DHB] - ${PLOTDIR}/"
echo "[DHB] Tiny boundary inspection passed."
