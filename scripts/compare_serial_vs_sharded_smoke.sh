#!/usr/bin/env bash
# scripts/compare_serial_vs_sharded_smoke.sh
# Purpose: Verify that serial and sharded evaluation produce equivalent output.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/setup_env.sh"

cd "${DHB_ROOT}"

# Create a clean scratch directory
SMOKE_DIR="${DHB_ROOT}/scratch/compare_smoke"
rm -rf "${SMOKE_DIR}"
mkdir -p "${SMOKE_DIR}"

echo "[DHB] Generating 100 fixed points..."
python3 scripts/generate_refined_lhs_boundary.py \
    --output "${SMOKE_DIR}/points.csv" \
    --n-points 100 \
    --seed 12345

# Ensure evaluate_point is compiled
echo "[DHB] Compiling evaluate_point if needed..."
./scripts/build_evaluate_point.sh

# Run serial
echo "[DHB] Running serial evaluation..."
./build/bin/evaluate_point "${SMOKE_DIR}/points.csv" "${SMOKE_DIR}/serial_out.csv" > "${SMOKE_DIR}/serial.log" 2>&1

# Run sharded
echo "[DHB] Splitting into 4 shards..."
python3 scripts/split_point_csv.py \
    --input "${SMOKE_DIR}/points.csv" \
    --outdir "${SMOKE_DIR}/shards" \
    --n-shards 4

echo "[DHB] Running shard evaluations in parallel..."
declare -A pids
for i in {0..3}; do
  shard_id=$(printf "%03d" "$i")
  shard_dir="${SMOKE_DIR}/shards/shard_${shard_id}"
  ./build/bin/evaluate_point "${shard_dir}/points.csv" "${shard_dir}/evaluate_point.csv" > "${shard_dir}/evaluate_point.log" 2>&1 &
  pids[$i]=$!
done

for i in {0..3}; do
  wait "${pids[$i]}"
done

echo "[DHB] Merging shard outputs..."
python3 scripts/merge_shard_outputs.py \
    --shards-dir "${SMOKE_DIR}/shards" \
    --output "${SMOKE_DIR}/sharded_out.csv"

echo "[DHB] Comparing serial and sharded CSV outputs..."
if diff -u "${SMOKE_DIR}/serial_out.csv" "${SMOKE_DIR}/sharded_out.csv" > "${SMOKE_DIR}/diff.patch" 2>&1; then
  echo "[DHB] SUCCESS: Serial and sharded CSV outputs are identical!"
  exit 0
else
  echo "[DHB] FAIL: Mismatch detected between serial and sharded CSV outputs!" >&2
  cat "${SMOKE_DIR}/diff.patch" | head -n 50 >&2
  exit 1
fi
