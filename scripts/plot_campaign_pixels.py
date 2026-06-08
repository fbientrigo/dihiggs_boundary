#!/usr/bin/env python3
# scripts/plot_campaign_pixels.py
# Purpose: Generate pixel plots from campaign index.
# Usage: python3 scripts/plot_campaign_pixels.py --campaign-dir campaigns/refined_lhs_v1 --bins auto

import argparse
import csv
import math
import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate pixel plots from campaign index.")
    p.add_argument("--campaign-dir", required=True, help="Path to campaign directory.")
    p.add_argument("--bins", default="auto", help="Number of bins (integer or 'auto').")
    p.add_argument("--target-count-per-pixel", type=int, default=5, help="Target count per pixel for auto binning.")
    p.add_argument("--progress-every-rows", type=int, default=500000, help="Print progress every N rows.")
    p.add_argument("--max-rows", type=int, default=None, help="Only process the first N rows from the campaign index.")
    return p

PAIRS = [
    ('mH', 'M'),
    ('mH', 'lambda6_input'),
    ('M', 'lambda6_input'),
    ('tan_beta', 'lambda6_input'),
    ('mH', 'tan_beta'),
    ('mH', 'mA'),
]

VARIABLES = ('mH', 'mA', 'M', 'tan_beta', 'lambda6_input')
FLAGS = ("theory_ok", "stu_ok", "physics_ok")
LOG_VARS = {'tan_beta', 'lambda6_input'}

def validate_columns(path: Path, required_columns: set) -> None:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
    missing = sorted(required_columns - fieldnames)
    if missing:
        print(f"[DHB] ERROR: Missing required columns in {path}: {', '.join(missing)}")
        sys.exit(1)

def iter_rows(path: Path, max_rows):
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=1):
            if max_rows is not None and row_index > max_rows:
                break
            yield row_index, row

def plot_value(raw_value: str, var_name: str):
    value = float(raw_value)
    if not math.isfinite(value):
        return None
    if var_name in LOG_VARS:
        if value <= 0.0:
            return None
        return math.log10(value)
    return value

def update_minmax(stats: dict, var_name: str, value: float) -> None:
    stats[var_name]["valid"] += 1
    if value < stats[var_name]["min"]:
        stats[var_name]["min"] = value
    if value > stats[var_name]["max"]:
        stats[var_name]["max"] = value

def get_bin_index(edges, value: float, bins: int):
    idx = int(np.searchsorted(edges, value, side="right") - 1)
    if idx < 0 or idx >= bins:
        return None
    return idx

def label_for_flag(flag: str) -> str:
    return 'Theory OK' if flag == 'theory_ok' else flag

def main():
    args = build_parser().parse_args()
    
    if not MATPLOTLIB_AVAILABLE:
        print("[DHB] ERROR: matplotlib or numpy is not available. Cannot generate plots.")
        sys.exit(1)

    campaign_dir = Path(args.campaign_dir)
    all_eval_csv = campaign_dir / "index" / "all_evaluate_point.csv"
    if not all_eval_csv.exists():
        print(f"[DHB] ERROR: Missing campaign index file: {all_eval_csv}")
        sys.exit(1)

    if args.max_rows is not None and args.max_rows < 0:
        print("[DHB] ERROR: --max-rows must be non-negative.")
        sys.exit(1)

    required_columns = set(VARIABLES) | set(FLAGS)
    validate_columns(all_eval_csv, required_columns)

    outdir = campaign_dir / "plots" / "pixel_plots"
    outdir.mkdir(parents=True, exist_ok=True)

    var_stats = {
        var: {"min": float("inf"), "max": float("-inf"), "valid": 0, "invalid": 0}
        for var in VARIABLES
    }

    N = 0
    for row_index, row in iter_rows(all_eval_csv, args.max_rows):
        N += 1
        for var in VARIABLES:
            try:
                value = plot_value(row[var], var)
            except ValueError as e:
                print(f"[DHB] ERROR: Invalid numeric value for {var} at data row {row_index}: {row[var]!r} ({e})")
                sys.exit(1)
            if value is None:
                var_stats[var]["invalid"] += 1
            else:
                update_minmax(var_stats, var, value)

        if args.progress_every_rows > 0 and row_index % args.progress_every_rows == 0:
            print(f"[DHB] Pass 1 scanned {row_index} rows.")

    if N == 0:
        print("[DHB] ERROR: No points found in index file.")
        sys.exit(1)

    for var, stats in var_stats.items():
        if stats["valid"] == 0:
            if var in LOG_VARS:
                print(f"[DHB] ERROR: No finite positive values available for log-scaled variable {var}.")
            else:
                print(f"[DHB] ERROR: No finite values available for variable {var}.")
            sys.exit(1)
        if stats["invalid"]:
            print(f"[DHB][WARNING] Skipped {stats['invalid']} invalid values for {var} while computing plot ranges.")

    # Determine bins
    if args.bins == "auto":
        if args.target_count_per_pixel <= 0:
            print("[DHB] ERROR: --target-count-per-pixel must be positive.")
            sys.exit(1)
        calculated_bins = int(math.sqrt(N / args.target_count_per_pixel))
        bins = max(16, min(160, calculated_bins))
        print(f"[DHB] Auto-calculated bins: {bins} (N={N}, target={args.target_count_per_pixel})")
    else:
        try:
            bins = int(args.bins)
        except ValueError:
            print(f"[DHB] ERROR: Invalid bins value: {args.bins}. Use an integer or 'auto'.")
            sys.exit(1)
        if bins <= 0:
            print("[DHB] ERROR: --bins must be positive.")
            sys.exit(1)

    eps = 1e-9
    edges = {}
    for var, stats in var_stats.items():
        edges[var] = np.linspace(stats["min"] - eps, stats["max"] + eps, bins + 1)

    total_counts_by_pair = {
        pair: np.zeros((bins, bins), dtype=np.int64)
        for pair in PAIRS
    }
    ok_counts_by_pair = {
        pair: {flag: np.zeros((bins, bins), dtype=np.int64) for flag in FLAGS}
        for pair in PAIRS
    }
    skipped_by_pair = {pair: 0 for pair in PAIRS}

    for row_index, row in iter_rows(all_eval_csv, args.max_rows):
        values = {}
        for var in VARIABLES:
            try:
                values[var] = plot_value(row[var], var)
            except ValueError as e:
                print(f"[DHB] ERROR: Invalid numeric value for {var} at data row {row_index}: {row[var]!r} ({e})")
                sys.exit(1)

        flags = {flag: str(row.get(flag, '0')).strip() == '1' for flag in FLAGS}

        for pair in PAIRS:
            x_var, y_var = pair
            x_val = values[x_var]
            y_val = values[y_var]
            if x_val is None or y_val is None:
                skipped_by_pair[pair] += 1
                continue

            i = get_bin_index(edges[x_var], x_val, bins)
            j = get_bin_index(edges[y_var], y_val, bins)
            if i is None or j is None:
                skipped_by_pair[pair] += 1
                continue

            total_counts_by_pair[pair][i, j] += 1
            for flag, is_ok in flags.items():
                if is_ok:
                    ok_counts_by_pair[pair][flag][i, j] += 1

        if args.progress_every_rows > 0 and row_index % args.progress_every_rows == 0:
            print(f"[DHB] Pass 2 filled histograms from {row_index} rows.")

    for x_var, y_var in PAIRS:
        pair = (x_var, y_var)
        x_edges = edges[x_var]
        y_edges = edges[y_var]
        x_is_log = x_var in LOG_VARS
        y_is_log = y_var in LOG_VARS
        total_counts = total_counts_by_pair[pair]
        ok_counts_dict = ok_counts_by_pair[pair]

        if skipped_by_pair[pair]:
            print(f"[DHB][WARNING] Skipped {skipped_by_pair[pair]} rows for pair {x_var} vs {y_var} due to invalid plot coordinates.")

        # 1. Density heatmap (total counts)
        # Empty pixels must be visually distinct: set background of axis to light neutral gray
        density_masked = np.ma.masked_where(total_counts == 0, total_counts)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_facecolor('#e0e0e0')  # light gray
        mesh = ax.pcolormesh(x_edges, y_edges, density_masked.T, cmap='Blues')
        fig.colorbar(mesh, ax=ax, label='Total counts')
        ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
        ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
        ax.set_title(f"Density: {y_var} vs {x_var}")
        fig.tight_layout()
        fig.savefig(outdir / f"density_{x_var}_vs_{y_var}.png", dpi=150)
        plt.close(fig)

        for flag in FLAGS:
            ok_counts = ok_counts_dict[flag]
            # 2. Acceptance fraction heatmap ({flag} fraction)
            fraction = np.zeros_like(total_counts, dtype=float)
            mask = total_counts > 0
            fraction[mask] = ok_counts[mask] / total_counts[mask]
            
            fraction_masked = np.ma.masked_where(total_counts == 0, fraction)
            
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.set_facecolor('#e0e0e0')  # light gray
            mesh = ax.pcolormesh(x_edges, y_edges, fraction_masked.T, cmap='viridis', vmin=0, vmax=1)
            
            label_name = label_for_flag(flag)
            fig.colorbar(mesh, ax=ax, label=f'{label_name} fraction')
            ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
            ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
            
            title = f"Acceptance: {y_var} vs {x_var}" if flag == 'theory_ok' else f"Acceptance ({flag}): {y_var} vs {x_var}"
            ax.set_title(title)
            fig.tight_layout()
            
            outname = f"acceptance_{x_var}_vs_{y_var}.png" if flag == 'theory_ok' else f"acceptance_{flag}_{x_var}_vs_{y_var}.png"
            fig.savefig(outdir / outname, dpi=150)
            plt.close(fig)

            # 3. {flag} count heatmap ({flag} count)
            ok_masked = np.ma.masked_where(total_counts == 0, ok_counts)
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.set_facecolor('#e0e0e0')  # light gray
            mesh = ax.pcolormesh(x_edges, y_edges, ok_masked.T, cmap='Greens')
            fig.colorbar(mesh, ax=ax, label=f'{label_name} count')
            ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
            ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
            
            title = f"Theory OK Count: {y_var} vs {x_var}" if flag == 'theory_ok' else f"{label_name} Count: {y_var} vs {x_var}"
            ax.set_title(title)
            fig.tight_layout()
            
            outname = f"theory_ok_count_{x_var}_vs_{y_var}.png" if flag == 'theory_ok' else f"{flag}_count_{x_var}_vs_{y_var}.png"
            fig.savefig(outdir / outname, dpi=150)
            plt.close(fig)

            # Exists {flag} heatmap
            exists_data = np.where(ok_counts > 0, 1.0, 0.0)
            exists_masked = np.ma.masked_where(total_counts == 0, exists_data)
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.set_facecolor('#e0e0e0')  # light gray
            mesh = ax.pcolormesh(x_edges, y_edges, exists_masked.T, cmap='plasma', vmin=0, vmax=1)
            fig.colorbar(mesh, ax=ax, label=f'Exists {flag}')
            ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
            ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
            ax.set_title(f"Exists {flag}: {y_var} vs {x_var}")
            fig.tight_layout()
            fig.savefig(outdir / f"exists_{flag}_{x_var}_vs_{y_var}.png", dpi=150)
            plt.close(fig)

        # 4. Binned CSV
        csv_path = outdir / f"pixel_acceptance_{x_var}_vs_{y_var}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            
            headers = [x_var + "_bin_center", y_var + "_bin_center", "total_count"]
            for flag in FLAGS:
                headers.extend([f"{flag}_count", f"{flag}_fraction", f"exists_{flag}"])
            writer.writerow(headers)

            for i in range(bins):
                for j in range(bins):
                    c = total_counts[i, j]
                    if c > 0:
                        xc = (x_edges[i] + x_edges[i+1]) / 2
                        yc = (y_edges[j] + y_edges[j+1]) / 2
                        if x_is_log: xc = 10**xc
                        if y_is_log: yc = 10**yc
                        
                        row = [xc, yc, int(c)]
                        for flag in FLAGS:
                            ok = ok_counts_dict[flag][i, j]
                            frac_val = ok / c
                            exists_val = 1 if ok > 0 else 0
                            row.extend([int(ok), frac_val, exists_val])
                        
                        writer.writerow(row)

    print(f"[DHB] Binned pixel plots and CSVs successfully written to: {outdir}")
    return 0

if __name__ == "__main__":
    main()
