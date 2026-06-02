#!/usr/bin/env bash
# scripts/keep_working_lhs_campaign.sh
# Purpose: Run batches repeatedly for a time budget or until STOP_REQUESTED exists.
# Usage: scripts/keep_working_lhs_campaign.sh <campaign_id> <n_points_per_batch> <max_seconds> [base_seed]
#
# Defaults:
#   campaign_id: refined_lhs_v1
#   n_points_per_batch: 5000
#   max_seconds: 3600
#   base_seed: 12345
#
# Stop semantics:
#   Soft stop: touch campaigns/<campaign_id>/STOP_REQUESTED
#     The loop finishes the current batch and stops before the next batch.
#   Hard stop: Ctrl-C or kill the process.
#     Any batch_<N>.partial without DONE is considered incomplete and safe to delete.

set -euo pipefail

# Help text / usage check
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0 [campaign_id] [n_points_per_batch] [max_seconds] [base_seed]"
  echo "Defaults:"
  echo "  campaign_id:        refined_lhs_v1"
  echo "  n_points_per_batch: 5000"
  echo "  max_seconds:        3600"
  echo "  base_seed:          12345"
  echo ""
  echo "Soft Stop: touch campaigns/<campaign_id>/STOP_REQUESTED"
  echo "  Gracefully stops the campaign loop before starting the next batch."
  echo "Hard Stop: Ctrl-C or kill. Any batch_<N>.partial can be safely deleted."
  exit 0
fi

# Arguments & Defaults
CAMPAIGN_ID="${1:-refined_lhs_v1}"
N_POINTS="${2:-5000}"
MAX_SECONDS="${3:-3600}"
BASE_SEED="${4:-12345}"

# Source environment setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/setup_env.sh"

# Make sure we work relative to the project root
cd "${DHB_ROOT}"

# Determine campaign root
CAMPAIGN_ROOT="${DHB_CAMPAIGN_ROOT:-${DHB_ROOT}/campaigns}"
CAMPAIGN_DIR="${CAMPAIGN_ROOT}/${CAMPAIGN_ID}"
mkdir -p "${CAMPAIGN_DIR}"

STOP_FILE="${CAMPAIGN_DIR}/STOP_REQUESTED"

START_TIME=$(date +%s)

echo "=== Campaign Orchestrator Started ==="
echo "Campaign ID:          ${CAMPAIGN_ID}"
echo "Points per Batch:     ${N_POINTS}"
echo "Max Seconds:          ${MAX_SECONDS}"
echo "Base Seed:            ${BASE_SEED}"
echo "Campaign Directory:   ${CAMPAIGN_DIR}"
echo "Soft Stop File:       ${STOP_FILE}"
echo "====================================="

# If STOP_REQUESTED file exists at the start, remove it to allow starting fresh if desired, 
# or keep it if the user wants it. Let's print a warning if it exists.
if [ -f "${STOP_FILE}" ]; then
  echo "[DHB] WARNING: STOP_REQUESTED exists at ${STOP_FILE}. Removing it to start run."
  rm -f "${STOP_FILE}"
fi

while true; do
  # Check if soft stop has been requested
  if [ -f "${STOP_FILE}" ]; then
    echo "[DHB] STOP_REQUESTED file found at ${STOP_FILE}. Gracefully stopping campaign loop."
    # Clean up stop file so it does not block future runs
    rm -f "${STOP_FILE}"
    break
  fi

  # Check time budget
  CURRENT_TIME=$(date +%s)
  ELAPSED=$((CURRENT_TIME - START_TIME))
  if [ "${ELAPSED}" -ge "${MAX_SECONDS}" ]; then
    echo "[DHB] Time budget of ${MAX_SECONDS}s exceeded (elapsed: ${ELAPSED}s). Stopping campaign loop."
    break
  fi

  REMAINING=$((MAX_SECONDS - ELAPSED))
  echo "[DHB] Elapsed time: ${ELAPSED}s, Remaining: ${REMAINING}s."
  
  # Run batch
  set +e
  ./scripts/run_lhs_batch.sh "${CAMPAIGN_ID}" "${N_POINTS}" "${BASE_SEED}"
  BATCH_EXIT_CODE=$?
  set -e

  if [ $BATCH_EXIT_CODE -ne 0 ]; then
    echo "ERROR: Batch run failed with exit code $BATCH_EXIT_CODE. Aborting loop." >&2
    exit $BATCH_EXIT_CODE
  fi

  echo "[DHB] Batch completed successfully."
done

# Run rebuild campaign index at the end
echo "[DHB] Campaign finished. Rebuilding derived index..."
python3 scripts/rebuild_campaign_index.py --campaign-dir "${CAMPAIGN_DIR}"

# Run check campaign integrity at the end
echo "[DHB] Running campaign integrity checks..."
python3 scripts/check_campaign_integrity.py --campaign-dir "${CAMPAIGN_DIR}"

echo "[DHB] Orchestrator finished."
