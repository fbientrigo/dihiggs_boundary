#!/usr/bin/env python3
import os
import csv
import json
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Merge shard evaluate_point.csv outputs.")
    parser.add_argument("--shards-dir", required=True, help="Directory containing shard folders")
    parser.add_argument("--output", required=True, help="Path to merge output evaluate_point.csv")
    args = parser.parse_args()

    # Determine expected shards
    manifest_path = os.path.join(args.shards_dir, "shards_manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            n_shards = manifest_data["n_shards"]
            shard_dirs = [os.path.join(args.shards_dir, f"shard_{i:03d}") for i in range(n_shards)]
        except Exception as e:
            print(f"Error reading shards manifest: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Fallback: scan shards-dir
        if not os.path.exists(args.shards_dir):
            print(f"Error: Shards directory {args.shards_dir} does not exist", file=sys.stderr)
            sys.exit(1)
        import glob
        shard_dirs = sorted(glob.glob(os.path.join(args.shards_dir, "shard_[0-9]*")))

    if not shard_dirs:
        print(f"Error: No shard directories found in {args.shards_dir}", file=sys.stderr)
        sys.exit(1)

    merged_rows = 0
    per_shard_rows = []
    header = None
    all_rows = []

    for sdir in shard_dirs:
        csv_path = os.path.join(sdir, "evaluate_point.csv")
        if not os.path.exists(csv_path):
            print(f"Error: Missing evaluate_point.csv in shard {sdir}", file=sys.stderr)
            sys.exit(1)

        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                shard_header = next(reader)
            except StopIteration:
                print(f"Error: Shard CSV {csv_path} is empty", file=sys.stderr)
                sys.exit(1)

            if header is None:
                header = shard_header
            else:
                if shard_header != header:
                    print(f"Error: Header mismatch in shard {sdir}", file=sys.stderr)
                    print(f"Expected: {header}", file=sys.stderr)
                    print(f"Found:    {shard_header}", file=sys.stderr)
                    sys.exit(1)

            shard_rows = list(reader)
            per_shard_rows.append(len(shard_rows))
            merged_rows += len(shard_rows)
            all_rows.extend(shard_rows)

    # Write final output
    output_dir = os.path.dirname(os.path.abspath(args.output))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(all_rows)

    # Write merge manifest
    merge_manifest_path = os.path.join(output_dir, "evaluate_point.merge_manifest.json")
    merge_manifest_data = {
        "shard_count": len(shard_dirs),
        "per_shard_rows": per_shard_rows,
        "merged_rows": merged_rows
    }

    with open(merge_manifest_path, "w", encoding="utf-8") as f_manifest:
        json.dump(merge_manifest_data, f_manifest, indent=2)

    print(f"Successfully merged {len(shard_dirs)} shards into {args.output} ({merged_rows} rows).")

if __name__ == "__main__":
    main()
