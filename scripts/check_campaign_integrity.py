#!/usr/bin/env python3
# scripts/check_campaign_integrity.py
# Purpose: Validate campaign consistency and integrity.
# Usage: python3 scripts/check_campaign_integrity.py --campaign-dir campaigns/refined_lhs_v1

import argparse
import csv
import json
from pathlib import Path

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check integrity of campaign batches and indices.")
    p.add_argument("--campaign-dir", required=True, help="Path to the campaign directory.")
    return p

def count_csv_rows(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0
        rows = 0
        for row in reader:
            if row and any(cell.strip() for cell in row):
                rows += 1
        return rows

def main():
    args = build_parser().parse_args()
    campaign_dir = Path(args.campaign_dir)
    if not campaign_dir.exists():
        raise SystemExit(f"[DHB][FAIL] Campaign directory does not exist: {campaign_dir}")

    batches_dir = campaign_dir / "batches"
    if not batches_dir.exists():
        raise SystemExit(f"[DHB][FAIL] Batches directory does not exist in: {campaign_dir}")

    completed_batches = []
    partial_batches = []

    # Identify completed and partial batches
    for p in batches_dir.iterdir():
        if p.is_dir():
            if p.name.endswith(".partial"):
                partial_batches.append(p)
            else:
                completed_batches.append(p)

    print(f"[DHB] Found {len(completed_batches)} completed batch directories.")
    print(f"[DHB] Found {len(partial_batches)} partial batch directories.")

    # Report partial batches separately
    if partial_batches:
        print("[DHB] Partial batches (safe to delete if interrupted):")
        for pb in sorted(partial_batches):
            print(f"  - {pb.name}")

    integrity_failed = False
    sum_completed_rows = 0
    seen_batch_ids = set()

    EXPECTED_Z2_WARNING = "WARNING: Requested Yukawa type respects Z2-symmetry but lambda6 or lambda7 is not zero"

    # Validate each completed batch
    for cb in sorted(completed_batches, key=lambda p: p.name):
        print(f"[DHB] Checking completed batch: {cb.name}")
        seen_batch_ids.add(cb.name)

        # 1. Each completed batch must have DONE marker
        done_marker = cb / "DONE"
        if not done_marker.exists():
            print(f"  [FAIL] Missing DONE marker in completed batch directory: {cb.name}")
            integrity_failed = True
            continue

        # 2. Each completed batch must have points.csv, evaluate_point.csv, manifest.json
        points_csv = cb / "points.csv"
        eval_csv = cb / "evaluate_point.csv"
        manifest_json = cb / "manifest.json"
        raw_log = cb / "evaluate_point.log.raw"
        filtered_log = cb / "evaluate_point.log"

        missing_files = []
        for f in [points_csv, eval_csv, manifest_json, raw_log, filtered_log]:
            if not f.exists():
                missing_files.append(f.name)

        if missing_files:
            print(f"  [FAIL] Missing required files in {cb.name}: {', '.join(missing_files)}")
            integrity_failed = True
            continue

        # 3. Count rows and verify input_rows == output_rows
        try:
            in_rows = count_csv_rows(points_csv)
            out_rows = count_csv_rows(eval_csv)
        except Exception as e:
            print(f"  [FAIL] Error reading CSVs in {cb.name}: {e}")
            integrity_failed = True
            continue

        if in_rows != out_rows:
            print(f"  [FAIL] Input rows ({in_rows}) != Output rows ({out_rows}) in {cb.name}")
            integrity_failed = True

        sum_completed_rows += out_rows

        # 4. Validate manifest status is success and contains matching rows
        try:
            with manifest_json.open("r") as mf:
                mdata = json.load(mf)
        except Exception as e:
            print(f"  [FAIL] Error parsing manifest.json in {cb.name}: {e}")
            integrity_failed = True
            continue

        if mdata.get("status") != "success":
            print(f"  [FAIL] Manifest status is not success in {cb.name}: {mdata.get('status')}")
            integrity_failed = True

        if mdata.get("input_rows") != in_rows or mdata.get("output_rows") != out_rows:
            print(f"  [FAIL] Manifest row count ({mdata.get('input_rows')}/{mdata.get('output_rows')}) "
                  f"does not match actual count ({in_rows}/{out_rows}) in {cb.name}")
            integrity_failed = True

        # 5. Check warning count logic
        # expected warning count in raw log is >= filtered warning count
        # filtered expected warning count should be 0.
        try:
            with raw_log.open("r", encoding="utf-8", errors="ignore") as f:
                raw_warnings = sum(1 for line in f if EXPECTED_Z2_WARNING in line)
            with filtered_log.open("r", encoding="utf-8", errors="ignore") as f:
                filt_warnings = sum(1 for line in f if EXPECTED_Z2_WARNING in line)
        except Exception as e:
            print(f"  [FAIL] Error reading logs in {cb.name}: {e}")
            integrity_failed = True
            continue

        m_raw_count = mdata.get("expected_z2_warning_count", -1)
        m_filt_count = mdata.get("filtered_z2_warning_count", -1)

        if raw_warnings != m_raw_count:
            print(f"  [FAIL] Counted raw Z2 warnings ({raw_warnings}) does not match manifest count ({m_raw_count}) in {cb.name}")
            integrity_failed = True

        if filt_warnings != m_filt_count:
            print(f"  [FAIL] Counted filtered Z2 warnings ({filt_warnings}) does not match manifest count ({m_filt_count}) in {cb.name}")
            integrity_failed = True

        if filt_warnings != 0:
            print(f"  [FAIL] Expected Z2 warnings found in filtered log: {filt_warnings} occurrences in {cb.name}")
            integrity_failed = True

        if raw_warnings < filt_warnings:
            print(f"  [FAIL] Expected Z2 warning count in raw log ({raw_warnings}) < filtered warning count ({filt_warnings}) in {cb.name}")
            integrity_failed = True

        print(f"  [OK] Batch {cb.name} checked. {out_rows} points. Warnings: {raw_warnings} raw / {filt_warnings} filtered.")

    # 6. If index/all_evaluate_point.csv exists, its row count matches sum of completed batches.
    all_eval_csv = campaign_dir / "index" / "all_evaluate_point.csv"
    if all_eval_csv.exists():
        try:
            indexed_rows = count_csv_rows(all_eval_csv)
            if indexed_rows != sum_completed_rows:
                print(f"[FAIL] Derived index row count ({indexed_rows}) does not match sum of completed batches ({sum_completed_rows})")
                integrity_failed = True
            else:
                print(f"[OK] Derived index row count matches sum of completed batches: {indexed_rows} rows.")
        except Exception as e:
            print(f"[FAIL] Error verifying index/all_evaluate_point.csv: {e}")
            integrity_failed = True
    else:
        print("[DHB] Derived index index/all_evaluate_point.csv does not exist yet. Run rebuild_campaign_index.py.")

    if integrity_failed:
        print("[DHB][FAIL] Campaign integrity check FAILED.")
        raise SystemExit(1)
    else:
        print("[DHB][OK] Campaign integrity check PASSED.")
        return 0

if __name__ == "__main__":
    main()
