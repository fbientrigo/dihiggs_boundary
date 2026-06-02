#!/usr/bin/env bash
# scripts/run_lhs_batch.sh
# Purpose: Run exactly one campaign batch of Latin Hypercube samples.
# Usage: scripts/run_lhs_batch.sh <campaign_id> <n_points> <base_seed>

set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <campaign_id> <n_points> <base_seed>" >&2
  exit 1
fi

CAMPAIGN_ID="$1"
N_POINTS="$2"
BASE_SEED="$3"

# Source environment setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/setup_env.sh"

# Make sure we work relative to the project root
cd "${DHB_ROOT}"

# Determine campaign root from DHB_CAMPAIGN_ROOT or default to campaigns
CAMPAIGN_ROOT="${DHB_CAMPAIGN_ROOT:-${DHB_ROOT}/campaigns}"
CAMPAIGN_DIR="${CAMPAIGN_ROOT}/${CAMPAIGN_ID}"
mkdir -p "${CAMPAIGN_DIR}"

# Create campaign.yaml if missing
YAML_PATH="${CAMPAIGN_DIR}/campaign.yaml"
if [ ! -f "${YAML_PATH}" ]; then
  cat << EOF > "${YAML_PATH}"
campaign_id: ${CAMPAIGN_ID}
created_at_utc: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
parameter_ranges:
  mH: "linear 240 to 360"
  mA: "linear 280 to 650"
  M: "linear 200 to 450"
  tan_beta: "log10-uniform 10 to 10000"
  lambda6: "log10-uniform 1e-12 to 1e-2"
yukawa_assignment: "type-I"
potential_type: "hard-Z2-breaking"
notes: "CP-conserving 2HDM with Type-I Yukawa assignment and nonzero lambda6 (hard-Z2-breaking scalar potential)."
EOF
  echo "[DHB] Created campaign.yaml for campaign: ${CAMPAIGN_ID}"
fi

# Determine next batch number by scanning completed batch directories and partial directories
BATCHES_DIR="${CAMPAIGN_DIR}/batches"
mkdir -p "${BATCHES_DIR}"

NEXT_NUM=1
# Scan both normal and partial directories matching batch_[0-9]*
for d in "${BATCHES_DIR}"/batch_[0-9]* "${BATCHES_DIR}"/batch_[0-9]*.partial; do
  if [ -d "$d" ]; then
    bname=$(basename "$d")
    num_str=$(echo "$bname" | sed -E 's/batch_([0-9]+)(\.partial)?/\1/')
    # Force decimal interpretation
    num=$((10#$num_str))
    if [ "$num" -ge "$NEXT_NUM" ]; then
      NEXT_NUM=$((num + 1))
    fi
  fi
done

BATCH_NUM="$NEXT_NUM"
BATCH_ID=$(printf "batch_%06d" "${BATCH_NUM}")
PARTIAL_DIR="${BATCHES_DIR}/${BATCH_ID}.partial"
FINAL_DIR="${BATCHES_DIR}/${BATCH_ID}"

# Refuse to overwrite existing completed batch
if [ -d "${FINAL_DIR}" ]; then
  echo "ERROR: Completed batch directory ${FINAL_DIR} already exists!" >&2
  exit 1
fi

# Clean up any leftover partial run directory of this exact batch ID if it somehow exists
if [ -d "${PARTIAL_DIR}" ]; then
  echo "[DHB] Cleaning up existing partial directory ${PARTIAL_DIR}"
  rm -rf "${PARTIAL_DIR}"
fi

mkdir -p "${PARTIAL_DIR}"
DATE_STARTED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "=== Campaign ${CAMPAIGN_ID} - Starting Batch ${BATCH_ID} ==="
echo "N_POINTS: ${N_POINTS}"
echo "BASE_SEED: ${BASE_SEED}"
echo "BATCH_NUM: ${BATCH_NUM}"
BATCH_SEED=$((BASE_SEED + BATCH_NUM))
echo "BATCH_SEED: ${BATCH_SEED}"
echo "PARTIAL_DIR: ${PARTIAL_DIR}"

# Run base checks
echo "[DHB] Checking base..."
./scripts/check_base_ready.sh

# Build evaluate_point
echo "[DHB] Building evaluate_point..."
./scripts/build_evaluate_point.sh

# Generate points using existing generate_refined_lhs_boundary.py
echo "[DHB] Generating LHS points..."
python3 scripts/generate_refined_lhs_boundary.py \
    --output "${PARTIAL_DIR}/points.csv" \
    --n-points "${N_POINTS}" \
    --seed "${BATCH_SEED}"

# Rewrite point_id values after generation so they include campaign_id and batch id.
# Keep the same CSV header.
echo "[DHB] Rewriting point IDs..."
python3 -c "
import csv
path = '${PARTIAL_DIR}/points.csv'
campaign_id = '${CAMPAIGN_ID}'
batch_id = '${BATCH_ID}'
with open(path, 'r', newline='') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

with open(path, 'w', newline='') as f:
    writer = csv.writer(f, lineterminator='\n')
    writer.writerow(header)
    for i, row in enumerate(rows):
        new_id = f'{campaign_id}_{batch_id}_{i:06d}'
        row[0] = new_id
        writer.writerow(row)
"

# Validate input with check_point_input_csv.sh
echo "[DHB] Validating input CSV..."
./scripts/check_point_input_csv.sh "${PARTIAL_DIR}/points.csv" "${N_POINTS}"

# Run build/bin/evaluate_point points.csv evaluate_point.csv
echo "[DHB] Running physics evaluation (evaluate_point)..."
set +e
./build/bin/evaluate_point "${PARTIAL_DIR}/points.csv" "${PARTIAL_DIR}/evaluate_point.csv" > "${PARTIAL_DIR}/evaluate_point.log.raw" 2>&1
EVAL_EXIT_CODE=$?
set -e

# Preserve evaluate_point.log.raw. Filter expected Z2 warning into clean logs.
# EXPECTED WARNING: WARNING: Requested Yukawa type respects Z2-symmetry but lambda6 or lambda7 is not zero
EXPECTED_Z2_WARNING="WARNING: Requested Yukawa type respects Z2-symmetry but lambda6 or lambda7 is not zero"
grep -v "${EXPECTED_Z2_WARNING}" "${PARTIAL_DIR}/evaluate_point.log.raw" > "${PARTIAL_DIR}/evaluate_point.log" || true

RAW_WARNING_COUNT=$(grep -c "${EXPECTED_Z2_WARNING}" "${PARTIAL_DIR}/evaluate_point.log.raw" || true)
FILTERED_WARNING_COUNT=$(grep -c "${EXPECTED_Z2_WARNING}" "${PARTIAL_DIR}/evaluate_point.log" || true)

# Preserve true evaluate_point exit code
if [ $EVAL_EXIT_CODE -ne 0 ]; then
  echo "ERROR: evaluate_point failed with exit code $EVAL_EXIT_CODE" >&2
  exit $EVAL_EXIT_CODE
fi

# Validate output with check_evaluate_point_output.sh
echo "[DHB] Validating output CSV..."
./scripts/check_evaluate_point_output.sh "${PARTIAL_DIR}/evaluate_point.csv"

# Enforce input_rows == output_rows
INPUT_ROWS=$(tail -n +2 "${PARTIAL_DIR}/points.csv" | sed '/^[[:space:]]*$/d' | wc -l)
OUTPUT_ROWS=$(tail -n +2 "${PARTIAL_DIR}/evaluate_point.csv" | sed '/^[[:space:]]*$/d' | wc -l)

if [ "${INPUT_ROWS}" -ne "${OUTPUT_ROWS}" ]; then
  echo "ERROR: Input rows (${INPUT_ROWS}) does not match output rows (${OUTPUT_ROWS})!" >&2
  exit 1
fi

DATE_FINISHED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --porcelain | tr '\n' ',' | sed 's/,$//')
GPP_VERSION=$(g++ --version | head -n 1)
GSL_VERSION=$(gsl-config --version || echo "unknown")
HOSTNAME=$(hostname)

# Write manifest.json
echo "[DHB] Writing manifest.json..."
python3 -c "
import json
manifest = {
    'campaign_id': '${CAMPAIGN_ID}',
    'batch_id': '${BATCH_ID}',
    'batch_number': ${BATCH_NUM},
    'n_points_requested': ${N_POINTS},
    'input_rows': ${INPUT_ROWS},
    'output_rows': ${OUTPUT_ROWS},
    'base_seed': ${BASE_SEED},
    'batch_seed': ${BATCH_SEED},
    'git_commit': '${GIT_COMMIT}',
    'git_status_short': '${GIT_STATUS}',
    'date_started_utc': '${DATE_STARTED}',
    'date_finished_utc': '${DATE_FINISHED}',
    'hostname': '${HOSTNAME}',
    'gpp_version': '${GPP_VERSION}',
    'gsl_version': '${GSL_VERSION}',
    'dhb_root': '${DHB_ROOT}',
    'campaign_root': '${CAMPAIGN_ROOT}',
    'points_csv': 'batches/${BATCH_ID}/points.csv',
    'evaluate_point_csv': 'batches/${BATCH_ID}/evaluate_point.csv',
    'raw_log': 'batches/${BATCH_ID}/evaluate_point.log.raw',
    'filtered_log': 'batches/${BATCH_ID}/evaluate_point.log',
    'expected_z2_warning_count': ${RAW_WARNING_COUNT},
    'filtered_z2_warning_count': ${FILTERED_WARNING_COUNT},
    'status': 'success'
}
with open('${PARTIAL_DIR}/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)
"

# Create DONE only after everything passes
touch "${PARTIAL_DIR}/DONE"

# Rename batch_<N>.partial to batch_<N>
mv "${PARTIAL_DIR}" "${FINAL_DIR}"

echo "[DHB] Successfully completed Batch ${BATCH_ID}."
