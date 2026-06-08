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
    p.add_argument("--progress-every", type=int, default=25, help="Print progress every N batches.")
    p.add_argument("--max-batches", type=int, default=None, help="Only process the first N completed batches.")
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

def tmp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")

def write_rejection_counts(path: Path, rejection_counts: Counter, total_points: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rejection_stage", "count", "fraction"], lineterminator="\n")
        writer.writeheader()
        for stage, count in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            frac = float(count) / total_points if total_points else 0.0
            writer.writerow({
                "rejection_stage": stage,
                "count": count,
                "fraction": f"{frac:.17g}"
            })

def write_theory_summary(path: Path, flag_counts: dict, total_points: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
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

def write_campaign_summary(
    path: Path,
    campaign_dir: Path,
    total_completed_batches: int,
    total_points: int,
    flag_counts: dict,
    rejection_counts: Counter,
    duplicate_id_count: int,
    duplicate_hash_count: int,
    batch_metadata: list,
) -> None:
    theory_frac = float(flag_counts["theory_ok"]) / total_points if total_points else 0.0

    with path.open("w", encoding="utf-8") as f:
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

    found_completed_batches = len(completed_batches)
    print(f"[DHB] Found {found_completed_batches} completed batches.")

    if args.max_batches is not None:
        if args.max_batches < 0:
            raise SystemExit("[DHB][FAIL] --max-batches must be non-negative.")
        completed_batches = completed_batches[:args.max_batches]
        print(f"[DHB] Limiting rebuild to {len(completed_batches)} completed batches due to --max-batches.")

    total_completed_batches = len(completed_batches)

    if total_completed_batches == 0:
        print("[DHB] No completed batches to index. Exiting.")
        return 0

    header = None
    batch_metadata = []
    total_points = 0
    flag_counts = {col: 0 for col in FLAG_COLUMNS}
    rejection_counts = Counter()
    seen_point_ids = set()
    seen_point_hashes = set()
    duplicate_id_count = 0
    duplicate_hash_count = 0

    # Prepare index directory
    index_dir = campaign_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    all_eval_csv = index_dir / "all_evaluate_point.csv"
    point_hashes_txt = index_dir / "point_hashes.txt"
    rejection_csv = index_dir / "rejection_counts.csv"
    theory_summary_csv = index_dir / "theory_acceptance_summary.csv"
    summary_md = index_dir / "campaign_summary.md"

    final_paths = [all_eval_csv, point_hashes_txt, rejection_csv, theory_summary_csv, summary_md]
    tmp_paths = [tmp_path(p) for p in final_paths]
    for p in tmp_paths:
        if p.exists():
            p.unlink()

    # Process each batch
    with tmp_path(all_eval_csv).open("w", newline="", encoding="utf-8") as all_f, tmp_path(point_hashes_txt).open("w", encoding="utf-8") as hash_f:
        writer = None

        for batch_index, b in enumerate(completed_batches, start=1):
            eval_csv = b / "evaluate_point.csv"
            manifest_file = b / "manifest.json"

            if not (b / "DONE").exists():
                raise SystemExit(f"[DHB][FAIL] Completed batch is missing DONE marker: {b.name}")

            if not eval_csv.exists():
                raise SystemExit(f"[DHB][FAIL] Missing evaluate_point.csv in completed batch: {b.name}")

            # Try to load manifest for seed/rows info.
            seed_info = "unknown"
            if manifest_file.exists():
                try:
                    with manifest_file.open("r") as mf:
                        mdata = json.load(mf)
                        seed_info = mdata.get("batch_seed", "unknown")
                except Exception as e:
                    print(f"[DHB][WARNING] Failed to read manifest in {b.name}: {e}")

            batch_row_count = 0
            with eval_csv.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                batch_header = reader.fieldnames
                if not batch_header:
                    print(f"[DHB][WARNING] Empty evaluate_point.csv in batch: {b.name}")
                    continue

                if header is None:
                    header = batch_header
                    writer = csv.DictWriter(all_f, fieldnames=header, lineterminator="\n")
                    writer.writeheader()
                elif header != batch_header:
                    raise SystemExit(f"[DHB][FAIL] Header mismatch in batch {b.name} compared to previous batches!")

                for row in reader:
                    p_id = row["point_id"]
                    p_hash = get_canonical_hash(row)

                    if p_id in seen_point_ids:
                        duplicate_id_count += 1
                    else:
                        seen_point_ids.add(p_id)

                    if p_hash in seen_point_hashes:
                        duplicate_hash_count += 1
                    else:
                        seen_point_hashes.add(p_hash)

                    for col in FLAG_COLUMNS:
                        if str(row.get(col, "")).strip() == "1":
                            flag_counts[col] += 1
                    rejection_counts[row.get("rejection_stage", "unknown")] += 1

                    writer.writerow(row)
                    hash_f.write(f"{p_id} {p_hash}\n")
                    batch_row_count += 1
                    total_points += 1

            if batch_row_count == 0:
                print(f"[DHB][WARNING] No data rows in evaluate_point.csv for batch: {b.name}")

            batch_metadata.append({
                "batch_id": b.name,
                "rows": batch_row_count,
                "seed": seed_info
            })

            if args.progress_every > 0 and (batch_index % args.progress_every == 0 or batch_index == total_completed_batches):
                print(f"[DHB] Processed {batch_index}/{total_completed_batches} batches; {total_points} rows indexed.")

    if header is None:
        raise SystemExit("[DHB][FAIL] No readable evaluate_point.csv headers found in completed batches.")

    write_rejection_counts(tmp_path(rejection_csv), rejection_counts, total_points)
    write_theory_summary(tmp_path(theory_summary_csv), flag_counts, total_points)
    write_campaign_summary(
        tmp_path(summary_md),
        campaign_dir,
        total_completed_batches,
        total_points,
        flag_counts,
        rejection_counts,
        duplicate_id_count,
        duplicate_hash_count,
        batch_metadata,
    )

    for final_path in final_paths:
        tmp_path(final_path).replace(final_path)

    print(f"[DHB] Campaign index rebuilt successfully.")
    print(f"[DHB]   Merged CSV: {all_eval_csv}")
    fprint_path = str(summary_md)
    print(f"[DHB]   Summary MD: {fprint_path}")
    return 0

if __name__ == "__main__":
    main()
