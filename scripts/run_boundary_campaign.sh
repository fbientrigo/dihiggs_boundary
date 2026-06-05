#!/usr/bin/env bash
set -e

CONFIG=""
DRY_RUN=""
LIMIT_POINTS="0"
RESUME=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --config) CONFIG="$2"; shift ;;
        --dry-run) DRY_RUN="--dry-run" ;;
        --limit-points) LIMIT_POINTS="$2"; shift ;;
        --resume) RESUME="--resume" ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$CONFIG" ]]; then
    echo "Error: --config is required"
    exit 1
fi

echo "[DHB] Running boundary campaign..."
python3 scripts/run_boundary_campaign.py \
    --config "$CONFIG" \
    $DRY_RUN \
    --limit-points "$LIMIT_POINTS" \
    $RESUME

echo "[DHB] Campaign script finished successfully."
