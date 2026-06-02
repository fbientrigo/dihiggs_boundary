#!/usr/bin/env python3
import os
import csv
import json
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Split points.csv into shards.")
    parser.add_argument("--input", required=True, help="Path to input points.csv")
    parser.add_argument("--outdir", required=True, help="Output shards directory")
    parser.add_argument("--n-shards", type=int, required=True, help="Number of shards")
    args = parser.parse_args()

    if args.n_shards < 1:
        print("Error: n-shards must be >= 1", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: input file {args.input} does not exist", file=sys.stderr)
        sys.exit(1)

    # Read input CSV
    with open(args.input, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print("Error: Input CSV is empty", file=sys.stderr)
            sys.exit(1)
        rows = list(reader)

    total_rows = len(rows)
    n_shards = args.n_shards

    # Refuse n_shards < 1 (already done)
    # If n_shards > rows, create only as many non-empty shards as needed.
    if n_shards > total_rows:
        n_shards = max(1, total_rows)

    # Calculate row allocation
    # e.g., if total_rows = 10 and n_shards = 3:
    # 10 // 3 = 3 rows base, 10 % 3 = 1 extra row
    # Shard 0: 4 rows, Shard 1: 3 rows, Shard 2: 3 rows
    k, m = divmod(total_rows, n_shards)
    shard_allocations = []
    current_idx = 0
    for i in range(n_shards):
        num_rows = k + (1 if i < m else 0)
        shard_allocations.append((current_idx, current_idx + num_rows))
        current_idx += num_rows

    os.makedirs(args.outdir, exist_ok=True)

    per_shard_row_counts = []
    for i in range(n_shards):
        start_idx, end_idx = shard_allocations[i]
        shard_rows = rows[start_idx:end_idx]
        shard_dir = os.path.join(args.outdir, f"shard_{i:03d}")
        os.makedirs(shard_dir, exist_ok=True)
        
        shard_file = os.path.join(shard_dir, "points.csv")
        with open(shard_file, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(shard_rows)
            
        per_shard_row_counts.append(len(shard_rows))

    manifest_path = os.path.join(args.outdir, "shards_manifest.json")
    manifest_data = {
        "n_shards": n_shards,
        "total_rows": total_rows,
        "per_shard_row_counts": per_shard_row_counts
    }

    with open(manifest_path, "w", encoding="utf-8") as f_manifest:
        json.dump(manifest_data, f_manifest, indent=2)

    print(f"Successfully split {total_rows} rows into {n_shards} shards.")

if __name__ == "__main__":
    main()
