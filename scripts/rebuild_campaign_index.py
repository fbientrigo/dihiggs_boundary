#!/usr/bin/env python3
# scripts/rebuild_campaign_index.py
# Purpose: Rebuild derived campaign index from DONE batches.
# Usage: python3 scripts/rebuild_campaign_index.py --campaign-dir campaigns/refined_lhs_v1

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

FLAG_COLUMNS = [
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "triple_ok",
    "theory_ok",
]

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rebuild derived campaign index from completed batches.")
    p.add_argument("--campaign-dir", required=True, help="Path to the campaign directory.")
    return p

def get_canonical_hash(row) -> str:
    # coordinates: mH, mA, tan_beta, lambda6_input, M
    # use 17 significant digits in canonical strings
    coords = [
        f"{float(row['mH']):.17g}",
        f"{float(row['mA']):.17g}",
        f"{float(row['tan_beta']):.17g}",
        f"{float(row['lambda6_input']):.17g}",
        f"{float(row['M']):.17g}",
    ]
    canonical_string = ",".join(coords)
    return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

def main():
    args = build_parser().parse_args()
    campaign_dir = Path(args.campaign_dir)
    if not campaign_dir.exists():
        raise SystemExit(f"[DHB][FAIL] Campaign directory does not exist: {campaign_dir}")

    batches_dir = campaign_dir / "batches"
    if not batches_dir.exists():
        raise SystemExit(f"[DHB][FAIL] No batches directory found in: {campaign_dir}")

    # Find completed batches (directories that contain DONE marker)
    completed_batches = []
    for p in batches_dir.iterdir():
        if p.is_dir() and not p.name.endswith(".partial"):
            done_marker = p / "DONE"
            if done_marker.exists():
                completed_batches.append(p)

    # Sort batches by batch number extracted from batch_XXXXXX
    def extract_batch_num(p: Path) -> int:
        name = p.name
        if name.startswith("batch_"):
            try:
                return int(name.split("_")[1])
            except (IndexError, ValueError):
                return 999999
        return 999999

    completed_batches.sort(key=extract_batch_num)

    total_completed_batches = len(completed_batches)
    print(f"[DHB] Found {total_completed_batches} completed batches.")

    if total_completed_batches == 0:
        print("[DHB] No completed batches to index. Exiting.")
        return 0

    all_rows = []
    header = None
    point_ids = []
    point_hashes = []
    batch_metadata = []

    # Process each batch
    for b in completed_batches:
        eval_csv = b / "evaluate_point.csv"
        manifest_file = b / "manifest.json"
        
        if not eval_csv.exists():
            print(f"[DHB][WARNING] Missing evaluate_point.csv in completed batch: {b.name}")
            continue

        # Try to load manifest for seed/rows info
        seed_info = "unknown"
        n_points_reported = 0
        if manifest_file.exists():
            try:
                with manifest_file.open("r") as mf:
                    mdata = json.load(mf)
                    seed_info = mdata.get("batch_seed", "unknown")
                    n_points_reported = mdata.get("output_rows", 0)
            except Exception as e:
                print(f"[DHB][WARNING] Failed to read manifest in {b.name}: {e}")

        # Read CSV
        with eval_csv.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch_rows = list(reader)

        if not batch_rows:
            print(f"[DHB][WARNING] Empty evaluate_point.csv in batch: {b.name}")
            continue

        # Check header consistency
        batch_header = reader.fieldnames
        if header is None:
            header = batch_header
        elif header != batch_header:
            raise SystemExit(f"[DHB][FAIL] Header mismatch in batch {b.name} compared to previous batches!")

        # Process rows and compute coordinate hashes
        for row in batch_rows:
            p_id = row["point_id"]
            p_hash = get_canonical_hash(row)
            point_ids.append(p_id)
            point_hashes.append((p_id, p_hash))
            all_rows.append(row)

        batch_metadata.append({
            "batch_id": b.name,
            "rows": len(batch_rows),
            "seed": seed_info
        })

    # Prepare index directory
    index_dir = campaign_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # Write index/all_evaluate_point.csv
    all_eval_csv = index_dir / "all_evaluate_point.csv"
    with all_eval_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)

    # Write index/point_hashes.txt
    point_hashes_txt = index_dir / "point_hashes.txt"
    with point_hashes_txt.open("w", encoding="utf-8") as f:
        for p_id, p_hash in point_hashes:
            f.write(f"{p_id} {p_hash}\n")

    # Metrics computation
    total_points = len(all_rows)
    
    # Flag counts
    flag_counts = {}
    for col in FLAG_COLUMNS:
        count = sum(1 for row in all_rows if str(row.get(col, "")).strip() == "1")
        flag_counts[col] = count

    # Rejection stages
    rejection_counts = Counter(row.get("rejection_stage", "unknown") for row in all_rows)

    # Duplicates detection
    dup_id_counts = Counter(point_ids)
    duplicate_id_count = sum(count - 1 for count in dup_id_counts.values() if count > 1)

    hashes_only = [item[1] for item in point_hashes]
    dup_hash_counts = Counter(hashes_only)
    duplicate_hash_count = sum(count - 1 for count in dup_hash_counts.values() if count > 1)

    # Write index/rejection_counts.csv
    rejection_csv = index_dir / "rejection_counts.csv"
    with rejection_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rejection_stage", "count", "fraction"], lineterminator="\n")
        writer.writeheader()
        for stage, count in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            frac = float(count) / total_points if total_points else 0.0
            writer.writerow({
                "rejection_stage": stage,
                "count": count,
                "fraction": f"{frac:.17g}"
            })

    # Write index/theory_acceptance_summary.csv
    theory_summary_csv = index_dir / "theory_acceptance_summary.csv"
    with theory_summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "count", "fraction"], lineterminator="\n")
        writer.writeheader()
        writer.writerow({"metric": "total_points", "count": total_points, "fraction": "1.0"})
        for col in FLAG_COLUMNS:
            count = flag_counts[col]
            frac = float(count) / total_points if total_points else 0.0
            writer.writerow({
                "metric": col,
                "count": count,
                "fraction": f"{frac:.17g}"
            })

    # Write index/campaign_summary.md
    summary_md = index_dir / "campaign_summary.md"
    theory_frac = float(flag_counts["theory_ok"]) / total_points if total_points else 0.0

    with summary_md.open("w", encoding="utf-8") as f:
        f.write("# Campaign Summary Report\n\n")
        f.write(f"- **Campaign ID**: `{campaign_dir.name}`\n")
        f.write(f"- **Total Completed Batches**: `{total_completed_batches}`\n")
        f.write(f"- **Total Scanned Points**: `{total_points}`\n")
        f.write(f"- **Theory OK Count/Fraction**: `{flag_counts['theory_ok']}` / `{theory_frac:.6f}`\n")
        f.write(f"- **Duplicate point_id Count**: `{duplicate_id_count}`\n")
        f.write(f"- **Duplicate point_hash Count**: `{duplicate_hash_count}`\n\n")

        f.write("## Acceptance Flag Statistics\n\n")
        f.write("| Flag Metric | Count | Fraction |\n")
        f.write("|---|---:|---:|\n")
        for col in FLAG_COLUMNS:
            count = flag_counts[col]
            frac = float(count) / total_points if total_points else 0.0
            f.write(f"| `{col}` | {count} | {frac:.6f} |\n")

        f.write("\n## Rejection Stage Statistics\n\n")
        f.write("| Rejection Stage | Count | Fraction |\n")
        f.write("|---|---:|---:|\n")
        for stage, count in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            frac = float(count) / total_points if total_points else 0.0
            f.write(f"| `{stage}` | {count} | {frac:.6f} |\n")

        f.write("\n## Completed Batches List\n\n")
        f.write("| Batch ID | Rows Count | Batch Seed |\n")
        f.write("|---|---:|---:|\n")
        for bmeta in batch_metadata:
            f.write(f"| `{bmeta['batch_id']}` | {bmeta['rows']} | {bmeta['seed']} |\n")

    print(f"[DHB] Campaign index rebuilt successfully.")
    print(f"[DHB]   Merged CSV: {all_eval_csv}")
    fprint_path = str(summary_md)
    print(f"[DHB]   Summary MD: {fprint_path}")
    return 0

if __name__ == "__main__":
    main()
