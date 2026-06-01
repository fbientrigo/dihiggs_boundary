#!/usr/bin/env bash
set -e

N_POINTS=${1:-5000}
SEED=${2:-12345}

RUN_DIR="runs/refined_lhs_boundary"
mkdir -p "$RUN_DIR"

echo "=== Refined LHS Boundary Run ==="
echo "N_POINTS: $N_POINTS"
echo "SEED: $SEED"
echo "RUN_DIR: $RUN_DIR"

echo "Checking base..."
./scripts/check_base_ready.sh

echo "Building evaluate_point..."
./scripts/build_evaluate_point.sh

echo "Generating input..."
python3 scripts/generate_refined_lhs_boundary.py \
    --output "$RUN_DIR/points.csv" \
    --n-points "$N_POINTS" \
    --seed "$SEED"

echo "Checking input CSV..."
./scripts/check_point_input_csv.sh "$RUN_DIR/points.csv"

echo "Evaluating points..."
set +e
./build/bin/evaluate_point "$RUN_DIR/points.csv" "$RUN_DIR/evaluate_point.csv" > "$RUN_DIR/evaluate_point.log.raw" 2>&1
EVAL_EXIT_CODE=$?
set -e

# Filter log to keep only the actual failures or output minus the expected warning
grep -v "WARNING: Requested Yukawa type respects Z2-symmetry but lambda6 or lambda7 is not zero" "$RUN_DIR/evaluate_point.log.raw" > "$RUN_DIR/evaluate_point.log" || true

if [ $EVAL_EXIT_CODE -ne 0 ]; then
    echo "ERROR: evaluate_point failed with exit code $EVAL_EXIT_CODE"
    exit $EVAL_EXIT_CODE
fi

echo "Checking output CSV..."
./scripts/check_evaluate_point_output.sh "$RUN_DIR/evaluate_point.csv"

echo "Summarizing run..."
python3 scripts/summarize_boundary_run.py --input "$RUN_DIR/evaluate_point.csv" --outdir "$RUN_DIR"

echo "Inspecting boundary coordinates..."
python3 scripts/inspect_boundary_coordinates.py --input "$RUN_DIR/evaluate_point.csv" --outdir "$RUN_DIR"

echo "Plotting boundary pixels..."
python3 scripts/plot_boundary_pixels.py --input "$RUN_DIR/evaluate_point.csv" --outdir "$RUN_DIR/pixel_plots"

INPUT_ROWS=$(wc -l < "$RUN_DIR/points.csv")
OUTPUT_ROWS=$(wc -l < "$RUN_DIR/evaluate_point.csv")
if [ "$INPUT_ROWS" -ne "$OUTPUT_ROWS" ]; then
    echo "ERROR: input_rows ($INPUT_ROWS) != output_rows ($OUTPUT_ROWS)"
    exit 1
fi

echo "Writing run manifest..."
cat << EOF > "$RUN_DIR/run_manifest.txt"
run_type: refined_lhs_boundary
n_points: $N_POINTS
seed: $SEED
date: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
hostname: $(hostname)
git_commit: $(git rev-parse HEAD)
git_status: $(git status --porcelain | tr '\n' ',' | sed 's/,$//')
gxx_version: $(g++ --version | head -n 1)
gsl_version: $(gsl-config --version)
input_path: $RUN_DIR/points.csv
output_path: $RUN_DIR/evaluate_point.csv
input_rows: $INPUT_ROWS
output_rows: $OUTPUT_ROWS
status: success
EOF

echo "Done."
