#!/usr/bin/env bash
# scripts/run_lhs_batch_sharded.sh
# Purpose: Run exactly one campaign batch with N parallel evaluate_point processes.
# Usage: scripts/run_lhs_batch_sharded.sh <campaign_id> <n_points> <base_seed> <n_workers>

set -euo pipefail

# Defaults if arguments are missing
CAMPAIGN_ID="${1:-refined_lhs_v1}"
N_POINTS="${2:-5000}"
BASE_SEED="${3:-12345}"
N_WORKERS="${4:-4}"

# Source environment setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/setup_env.sh"

# Make sure we work relative to the project root
cd "${DHB_ROOT}"

# Determine campaign root from DHB_CAMPAIGN_ROOT or default to campaigns
CAMPAIGN_ROOT="${DHB_CAMPAIGN_ROOT:-${DHB_ROOT}/campaigns}"
CAMPAIGN_DIR="${CAMPAIGN_ROOT}/${CAMPAIGN_ID}"
mkdir -p "${CAMPAIGN_DIR}"

# Add simple campaign lock
LOCK_DIR="${CAMPAIGN_DIR}/.batch_lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "ERROR: Failed to acquire campaign batch lock: ${LOCK_DIR} already exists!" >&2
  exit 1
fi

# Clean up lock on exit
cleanup() {
  rm -rf "${LOCK_DIR}"
}
trap cleanup EXIT

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

echo "=== Campaign ${CAMPAIGN_ID} - Starting Sharded Batch ${BATCH_ID} ==="
echo "N_POINTS: ${N_POINTS}"
echo "BASE_SEED: ${BASE_SEED}"
echo "BATCH_NUM: ${BATCH_NUM}"
BATCH_SEED=$((BASE_SEED + BATCH_NUM))
echo "BATCH_SEED: ${BATCH_SEED}"
echo "N_WORKERS: ${N_WORKERS}"
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

# Split points.csv into shards using split_point_csv.py
echo "[DHB] Splitting points into shards..."
python3 scripts/split_point_csv.py \
    --input "${PARTIAL_DIR}/points.csv" \
    --outdir "${PARTIAL_DIR}/shards" \
    --n-shards "${N_WORKERS}"

# Get the actual number of shards created
SHARDS_MANIFEST="${PARTIAL_DIR}/shards/shards_manifest.json"
N_SHARDS_USED=$(python3 -c "import json; print(json.load(open('${SHARDS_MANIFEST}'))['n_shards'])")

# Launch one evaluate_point process per shard in background
declare -A shard_pids
for ((i=0; i<N_SHARDS_USED; i++)); do
  shard_id=$(printf "%03d" "$i")
  shard_dir="${PARTIAL_DIR}/shards/shard_${shard_id}"
  echo "[DHB] Starting shard ${shard_id} evaluation in background..."
  
  set +e
  ./build/bin/evaluate_point "${shard_dir}/points.csv" "${shard_dir}/evaluate_point.csv" > "${shard_dir}/evaluate_point.log.raw" 2>&1 &
  shard_pids[$i]=$!
  set -e
done

# Wait for all shards and preserve their exit codes
ANY_FAILED=0
declare -a per_shard_exit_codes
for ((i=0; i<N_SHARDS_USED; i++)); do
  pid=${shard_pids[$i]}
  set +e
  wait "$pid"
  code=$?
  set -e
  per_shard_exit_codes[$i]=$code
  if [ $code -ne 0 ]; then
    echo "ERROR: Shard $i (PID $pid) failed with exit code $code" >&2
    ANY_FAILED=1
  fi
done

# Convert exit codes array to comma-separated string for passing to python manifest writer
per_shard_exit_codes_str=""
for code in "${per_shard_exit_codes[@]}"; do
  if [ -z "${per_shard_exit_codes_str}" ]; then
    per_shard_exit_codes_str="$code"
  else
    per_shard_exit_codes_str="${per_shard_exit_codes_str},$code"
  fi
done

# If any shard failed, exit nonzero and leave partial dir in place
if [ "${ANY_FAILED}" -ne 0 ]; then
  echo "ERROR: One or more shards failed. Leaving ${PARTIAL_DIR} in place." >&2
  exit 1
fi

# Filter expected Yukawa warnings in shard logs
EXPECTED_Z2_WARNING="WARNING: Requested Yukawa type respects Z2-symmetry but lambda6 or lambda7 is not zero"
for ((i=0; i<N_SHARDS_USED; i++)); do
  shard_id=$(printf "%03d" "$i")
  shard_dir="${PARTIAL_DIR}/shards/shard_${shard_id}"
  if [ -f "${shard_dir}/evaluate_point.log.raw" ]; then
    grep -v "${EXPECTED_Z2_WARNING}" "${shard_dir}/evaluate_point.log.raw" > "${shard_dir}/evaluate_point.log" || true
  fi
done

# Validate every shard output with check_evaluate_point_output.sh
echo "[DHB] Validating shard output CSVs..."
for ((i=0; i<N_SHARDS_USED; i++)); do
  shard_id=$(printf "%03d" "$i")
  shard_dir="${PARTIAL_DIR}/shards/shard_${shard_id}"
  ./scripts/check_evaluate_point_output.sh "${shard_dir}/evaluate_point.csv"
done

# Merge shard outputs
echo "[DHB] Merging shard outputs..."
python3 scripts/merge_shard_outputs.py \
    --shards-dir "${PARTIAL_DIR}/shards" \
    --output "${PARTIAL_DIR}/evaluate_point.csv"

# Validate merged output
echo "[DHB] Validating merged output CSV..."
./scripts/check_evaluate_point_output.sh "${PARTIAL_DIR}/evaluate_point.csv"

# Enforce full input_rows == merged output_rows
INPUT_ROWS=$(tail -n +2 "${PARTIAL_DIR}/points.csv" | sed '/^[[:space:]]*$/d' | wc -l)
OUTPUT_ROWS=$(tail -n +2 "${PARTIAL_DIR}/evaluate_point.csv" | sed '/^[[:space:]]*$/d' | wc -l)

if [ "${INPUT_ROWS}" -ne "${OUTPUT_ROWS}" ]; then
  echo "ERROR: Input rows (${INPUT_ROWS}) does not match output rows (${OUTPUT_ROWS})!" >&2
  exit 1
fi

# Concatenate shard logs
echo "[DHB] Concatenating logs..."
> "${PARTIAL_DIR}/evaluate_point.log.raw"
for ((i=0; i<N_SHARDS_USED; i++)); do
  shard_id=$(printf "%03d" "$i")
  cat "${PARTIAL_DIR}/shards/shard_${shard_id}/evaluate_point.log.raw" >> "${PARTIAL_DIR}/evaluate_point.log.raw"
done

> "${PARTIAL_DIR}/evaluate_point.log"
for ((i=0; i<N_SHARDS_USED; i++)); do
  shard_id=$(printf "%03d" "$i")
  cat "${PARTIAL_DIR}/shards/shard_${shard_id}/evaluate_point.log" >> "${PARTIAL_DIR}/evaluate_point.log"
done

RAW_WARNING_COUNT=$(grep -c "${EXPECTED_Z2_WARNING}" "${PARTIAL_DIR}/evaluate_point.log.raw" || true)
FILTERED_WARNING_COUNT=$(grep -c "${EXPECTED_Z2_WARNING}" "${PARTIAL_DIR}/evaluate_point.log" || true)

# Write manifest.json
DATE_FINISHED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --porcelain | tr '\n' ',' | sed 's/,$//')
GPP_VERSION=$(g++ --version | head -n 1)
GSL_VERSION=$(gsl-config --version || echo "unknown")
HOSTNAME=$(hostname)

export DHB_PARTIAL_DIR="${PARTIAL_DIR}"
export DHB_CAMPAIGN_ID="${CAMPAIGN_ID}"
export DHB_BATCH_ID="${BATCH_ID}"
export DHB_BATCH_NUM="${BATCH_NUM}"
export DHB_N_POINTS="${N_POINTS}"
export DHB_INPUT_ROWS="${INPUT_ROWS}"
export DHB_OUTPUT_ROWS="${OUTPUT_ROWS}"
export DHB_BASE_SEED="${BASE_SEED}"
export DHB_BATCH_SEED="${BATCH_SEED}"
export DHB_N_WORKERS="${N_WORKERS}"
export DHB_N_SHARDS_USED="${N_SHARDS_USED}"
export DHB_PER_SHARD_EXIT_CODES="${per_shard_exit_codes_str}"
export DHB_GIT_COMMIT="${GIT_COMMIT}"
export DHB_GIT_STATUS="${GIT_STATUS}"
export DHB_DATE_STARTED="${DATE_STARTED}"
export DHB_DATE_FINISHED="${DATE_FINISHED}"
export DHB_HOSTNAME="${HOSTNAME}"
export DHB_GPP_VERSION="${GPP_VERSION}"
export DHB_GSL_VERSION="${GSL_VERSION}"
export DHB_DHB_ROOT="${DHB_ROOT}"
export DHB_CAMPAIGN_ROOT="${CAMPAIGN_ROOT}"
export DHB_RAW_WARNING_COUNT="${RAW_WARNING_COUNT}"
export DHB_FILTERED_WARNING_COUNT="${FILTERED_WARNING_COUNT}"

echo "[DHB] Writing manifest.json..."
python3 -c "
import os
import json

merge_manifest_path = os.path.join(os.environ['DHB_PARTIAL_DIR'], 'evaluate_point.merge_manifest.json')
with open(merge_manifest_path, 'r') as f:
    merge_data = json.load(f)
per_shard_rows = merge_data['per_shard_rows']

per_shard_exit_codes = [int(x) for x in os.environ['DHB_PER_SHARD_EXIT_CODES'].split(',') if x != '']

manifest = {
    'campaign_id': os.environ['DHB_CAMPAIGN_ID'],
    'batch_id': os.environ['DHB_BATCH_ID'],
    'batch_number': int(os.environ['DHB_BATCH_NUM']),
    'n_points_requested': int(os.environ['DHB_N_POINTS']),
    'input_rows': int(os.environ['DHB_INPUT_ROWS']),
    'output_rows': int(os.environ['DHB_OUTPUT_ROWS']),
    'base_seed': int(os.environ['DHB_BASE_SEED']),
    'batch_seed': int(os.environ['DHB_BATCH_SEED']),
    'n_workers_requested': int(os.environ['DHB_N_WORKERS']),
    'n_shards_used': int(os.environ['DHB_N_SHARDS_USED']),
    'per_shard_rows': per_shard_rows,
    'per_shard_exit_codes': per_shard_exit_codes,
    'git_commit': os.environ['DHB_GIT_COMMIT'],
    'git_status_short': os.environ['DHB_GIT_STATUS'],
    'date_started_utc': os.environ['DHB_DATE_STARTED'],
    'date_finished_utc': os.environ['DHB_DATE_FINISHED'],
    'hostname': os.environ['DHB_HOSTNAME'],
    'gpp_version': os.environ['DHB_GPP_VERSION'],
    'gsl_version': os.environ['DHB_GSL_VERSION'],
    'dhb_root': os.environ['DHB_DHB_ROOT'],
    'campaign_root': os.environ['DHB_CAMPAIGN_ROOT'],
    'points_csv': f'batches/{os.environ[\"DHB_BATCH_ID\"]}/points.csv',
    'evaluate_point_csv': f'batches/{os.environ[\"DHB_BATCH_ID\"]}/evaluate_point.csv',
    'expected_z2_warning_count': int(os.environ['DHB_RAW_WARNING_COUNT']),
    'filtered_z2_warning_count': int(os.environ['DHB_FILTERED_WARNING_COUNT']),
    'expected_z2_warning_count_raw': int(os.environ['DHB_RAW_WARNING_COUNT']),
    'expected_z2_warning_count_filtered': int(os.environ['DHB_FILTERED_WARNING_COUNT']),
    'status': 'success'
}

manifest_path = os.path.join(os.environ['DHB_PARTIAL_DIR'], 'manifest.json')
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)
"

# Create DONE file inside partial dir first
touch "${PARTIAL_DIR}/DONE"

# Atomic rename to final directory
mv "${PARTIAL_DIR}" "${FINAL_DIR}"

echo "[DHB] Successfully completed Sharded Batch ${BATCH_ID}."
