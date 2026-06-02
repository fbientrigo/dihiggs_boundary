#!/usr/bin/env python3
# scripts/plot_campaign_pixels.py
# Purpose: Generate pixel plots from campaign index.
# Usage: python3 scripts/plot_campaign_pixels.py --campaign-dir campaigns/refined_lhs_v1 --bins auto

import argparse
import csv
import math
import os
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
    return p

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

    outdir = campaign_dir / "plots" / "pixel_plots"
    outdir.mkdir(parents=True, exist_ok=True)

    # Load data
    data = {
        'mH': [], 'mA': [], 'M': [], 'tan_beta': [], 'lambda6_input': [], 'theory_ok': []
    }

    with all_eval_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data['mH'].append(float(row['mH']))
            data['mA'].append(float(row['mA']))
            data['M'].append(float(row['M']))
            data['tan_beta'].append(float(row['tan_beta']))
            data['lambda6_input'].append(float(row['lambda6_input']))
            data['theory_ok'].append(1 if str(row['theory_ok']).strip() == '1' else 0)

    for k in data:
        data[k] = np.array(data[k])

    N = len(data['theory_ok'])
    if N == 0:
        print("[DHB] ERROR: No points found in index file.")
        sys.exit(1)

    # Determine bins
    if args.bins == "auto":
        calculated_bins = int(math.sqrt(N / args.target_count_per_pixel))
        bins = max(16, min(160, calculated_bins))
        print(f"[DHB] Auto-calculated bins: {bins} (N={N}, target={args.target_count_per_pixel})")
    else:
        try:
            bins = int(args.bins)
        except ValueError:
            print(f"[DHB] ERROR: Invalid bins value: {args.bins}. Use an integer or 'auto'.")
            sys.exit(1)

    pairs = [
        ('mH', 'M'),
        ('mH', 'lambda6_input'),
        ('M', 'lambda6_input'),
        ('tan_beta', 'lambda6_input'),
        ('mH', 'tan_beta'),
        ('mH', 'mA'),
    ]

    log_vars = {'tan_beta', 'lambda6_input'}

    for x_var, y_var in pairs:
        x_data = data[x_var]
        y_data = data[y_var]
        theory_ok = data['theory_ok']

        x_is_log = x_var in log_vars
        y_is_log = y_var in log_vars

        x_plot = np.log10(x_data) if x_is_log else x_data
        y_plot = np.log10(y_data) if y_is_log else y_data

        x_min, x_max = np.min(x_plot), np.max(x_plot)
        y_min, y_max = np.min(y_plot), np.max(y_plot)

        # Padding to prevent edge cases
        eps = 1e-9
        x_edges = np.linspace(x_min - eps, x_max + eps, bins + 1)
        y_edges = np.linspace(y_min - eps, y_max + eps, bins + 1)

        total_counts, _, _ = np.histogram2d(x_plot, y_plot, bins=[x_edges, y_edges])
        ok_counts, _, _ = np.histogram2d(x_plot[theory_ok == 1], y_plot[theory_ok == 1], bins=[x_edges, y_edges])

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

        # 2. Acceptance fraction heatmap (theory_ok fraction)
        fraction = np.zeros_like(total_counts)
        mask = total_counts > 0
        fraction[mask] = ok_counts[mask] / total_counts[mask]
        
        fraction_masked = np.ma.masked_where(total_counts == 0, fraction)
        
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_facecolor('#e0e0e0')  # light gray
        mesh = ax.pcolormesh(x_edges, y_edges, fraction_masked.T, cmap='viridis', vmin=0, vmax=1)
        fig.colorbar(mesh, ax=ax, label='Theory OK fraction')
        ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
        ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
        ax.set_title(f"Acceptance: {y_var} vs {x_var}")
        fig.tight_layout()
        fig.savefig(outdir / f"acceptance_{x_var}_vs_{y_var}.png", dpi=150)
        plt.close(fig)

        # 3. Theory OK count heatmap (theory_ok count)
        ok_masked = np.ma.masked_where(total_counts == 0, ok_counts)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_facecolor('#e0e0e0')  # light gray
        mesh = ax.pcolormesh(x_edges, y_edges, ok_masked.T, cmap='Greens')
        fig.colorbar(mesh, ax=ax, label='Theory OK count')
        ax.set_xlabel(f"log10({x_var})" if x_is_log else x_var)
        ax.set_ylabel(f"log10({y_var})" if y_is_log else y_var)
        ax.set_title(f"Theory OK Count: {y_var} vs {x_var}")
        fig.tight_layout()
        fig.savefig(outdir / f"theory_ok_count_{x_var}_vs_{y_var}.png", dpi=150)
        plt.close(fig)

        # 4. Binned CSV
        csv_path = outdir / f"pixel_acceptance_{x_var}_vs_{y_var}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow([x_var + "_bin_center", y_var + "_bin_center", "total_count", "theory_ok_count", "theory_ok_fraction"])
            for i in range(bins):
                for j in range(bins):
                    c = total_counts[i, j]
                    if c > 0:
                        xc = (x_edges[i] + x_edges[i+1]) / 2
                        yc = (y_edges[j] + y_edges[j+1]) / 2
                        if x_is_log: xc = 10**xc
                        if y_is_log: yc = 10**yc
                        ok = ok_counts[i, j]
                        frac_val = ok / c
                        writer.writerow([xc, yc, int(c), int(ok), frac_val])

    print(f"[DHB] Binned pixel plots and CSVs successfully written to: {outdir}")
    return 0

if __name__ == "__main__":
    main()
