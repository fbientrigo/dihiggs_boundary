# Weekend Boundary Run

This document describes how to execute the weekend boundary campaign using the semi-automatic runner.

## Quick Start

### 1. Build the evaluator

Before running any campaign, build the underlying C++ evaluator:

```bash
./scripts/build_evaluate_point.sh
```

### 2. Dry-Run

Verify the configuration and grid generation without evaluating any physics points:

```bash
./scripts/run_boundary_campaign.sh --config configs/weekend_boundary_v0.yaml --dry-run
```

### 3. Tiny Test Run

Evaluate a small subset (e.g., 1000 points) to ensure the full pipeline, including CSV writing and plotting, works correctly:

```bash
./scripts/run_boundary_campaign.sh --config configs/weekend_boundary_v0.yaml --limit-points 1000
```

### 4. Weekend Run

Launch the full campaign inside `tmux` so it continues running after you disconnect.

```bash
tmux new -s weekend_run
./scripts/run_boundary_campaign.sh --config configs/weekend_boundary_v0.yaml --resume
```

Outputs are written to:
`/home/fabian/cern_db/dihiggs_lake/campaign=weekend_boundary_v0/`

## Monitoring Progress

Check the manifest file for the current status and the number of points evaluated:

```bash
cat /home/fabian/cern_db/dihiggs_lake/campaign=weekend_boundary_v0/manifest.json
```

Or view the generated plots in:
`/home/fabian/cern_db/dihiggs_lake/campaign=weekend_boundary_v0/plots/`

## Interruption and Resuming

To safely stop a run, simply send a `Ctrl+C` signal to the running script or terminate the `tmux` session. Since points are written atomically and tracked, you can resume at any time.

To resume an interrupted run:

```bash
./scripts/run_boundary_campaign.sh --config configs/weekend_boundary_v0.yaml --resume
```
