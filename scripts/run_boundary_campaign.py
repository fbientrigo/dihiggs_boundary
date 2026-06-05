#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import matplotlib.colors as mcolors
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def build_parser():
    p = argparse.ArgumentParser(description="Run semi-automatic boundary campaign.")
    p.add_argument("--config", required=True, help="Path to config YAML.")
    p.add_argument("--dry-run", action="store_true", help="Print actions but do not evaluate.")
    p.add_argument("--limit-points", type=int, default=0, help="Max points to evaluate (0 for unlimited).")
    p.add_argument("--resume", action="store_true", help="Resume from existing evaluate_point.csv.")
    return p


def get_git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        return "unknown"


def generate_points(config):
    points = []
    grid_size = config.get("grid_size", 20)
    fixed = config.get("fixed_parameters", {})
    pairs = config.get("variable_pairs", [])

    for p_idx, pair in enumerate(pairs):
        x_var = pair["x"]
        y_var = pair["y"]
        x_min, x_max = float(pair["x_min"]), float(pair["x_max"])
        y_min, y_max = float(pair["y_min"]), float(pair["y_max"])
        x_log = pair.get("x_log", False)
        y_log = pair.get("y_log", False)

        if x_log:
            x_vals = [10 ** v for v in (math.log10(x_min) + i * (math.log10(x_max) - math.log10(x_min)) / max(1, grid_size - 1) for i in range(grid_size))]
        else:
            x_vals = [x_min + i * (x_max - x_min) / max(1, grid_size - 1) for i in range(grid_size)]
            
        if y_log:
            y_vals = [10 ** v for v in (math.log10(y_min) + i * (math.log10(y_max) - math.log10(y_min)) / max(1, grid_size - 1) for i in range(grid_size))]
        else:
            y_vals = [y_min + i * (y_max - y_min) / max(1, grid_size - 1) for i in range(grid_size)]

        for i, x_val in enumerate(x_vals):
            for j, y_val in enumerate(y_vals):
                pt = dict(fixed)
                pt[x_var] = x_val
                pt[y_var] = y_val
                pt_id = f"p{p_idx}_{i}_{j}"
                pt["point_id"] = pt_id
                pt["_pair_idx"] = p_idx  # metadata
                pt["_x_var"] = x_var
                pt["_y_var"] = y_var
                points.append(pt)
    return points


def plot_existence_maps(main_csv, config, campaign_dir):
    if not MATPLOTLIB_AVAILABLE:
        print("[DHB] matplotlib not available, skipping plots.")
        return
    
    plots_dir = campaign_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all data
    data = []
    with main_csv.open("r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
            
    if not data:
        return
        
    pairs = config.get("variable_pairs", [])
    grid_size = config.get("grid_size", 20)
    flags = config.get("flags", {})
    
    plot_flags = [f for f in ["theory_ok", "stu_ok", "physics_ok"] if flags.get(f)]
    
    for pair in pairs:
        x_var = pair["x"]
        y_var = pair["y"]
        x_log = pair.get("x_log", False)
        y_log = pair.get("y_log", False)
        
        # Filter points that vary x and y but keep others fixed
        # It's easier to just take all points and bin them in x and y
        x_vals = [float(r[x_var]) for r in data]
        y_vals = [float(r[y_var]) for r in data]
        
        if not x_vals: continue
        
        x_plot = np.log10(x_vals) if x_log else np.array(x_vals)
        y_plot = np.log10(y_vals) if y_log else np.array(y_vals)
        
        x_min, x_max = np.min(x_plot), np.max(x_plot)
        y_min, y_max = np.min(y_plot), np.max(y_plot)
        
        eps = 1e-9
        x_edges = np.linspace(x_min - eps, x_max + eps, grid_size + 1)
        y_edges = np.linspace(y_min - eps, y_max + eps, grid_size + 1)
        
        for flag in plot_flags:
            ok_vals = [1 if str(r.get(flag, "0")).strip() == "1" else 0 for r in data]
            ok_arr = np.array(ok_vals)
            
            # We want exists: so if sum > 0, it's 1, else 0
            # Total counts first
            total_counts, _, _ = np.histogram2d(x_plot, y_plot, bins=[x_edges, y_edges])
            ok_counts, _, _ = np.histogram2d(x_plot[ok_arr == 1], y_plot[ok_arr == 1], bins=[x_edges, y_edges])
            
            exists = np.zeros_like(total_counts)
            exists[ok_counts > 0] = 1
            exists_masked = np.ma.masked_where(total_counts == 0, exists)
            
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.set_facecolor('#e0e0e0')  # light gray for empty bins
            
            cmap = mcolors.ListedColormap(['#d73027', '#1a9850']) # red for 0, green for 1
            bounds = [-0.5, 0.5, 1.5]
            norm = mcolors.BoundaryNorm(bounds, cmap.N)
            
            mesh = ax.pcolormesh(x_edges, y_edges, exists_masked.T, cmap=cmap, norm=norm)
            cbar = fig.colorbar(mesh, ax=ax, ticks=[0, 1])
            cbar.ax.set_yticklabels(['None Found', 'Exists'])
            
            ax.set_xlabel(f"log10({x_var})" if x_log else x_var)
            ax.set_ylabel(f"log10({y_var})" if y_log else y_var)
            ax.set_title(f"Exists {flag}: {y_var} vs {x_var}")
            fig.tight_layout()
            
            out_file = plots_dir / f"exists_{flag}_{x_var}_vs_{y_var}.png"
            fig.savefig(out_file, dpi=150)
            plt.close(fig)


def main():
    args = build_parser().parse_args()
    
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)
        
    campaign_name = config["campaign_name"]
    output_root = Path(config["output_root"])
    campaign_dir = output_root / f"campaign={campaign_name}"
    
    main_csv = campaign_dir / "evaluate_point.csv"
    manifest_path = campaign_dir / "manifest.json"
    
    if not args.dry_run:
        campaign_dir.mkdir(parents=True, exist_ok=True)
    
    all_points = generate_points(config)
    
    evaluated_ids = set()
    if args.resume and main_csv.exists():
        with open(main_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                evaluated_ids.add(row["point_id"])
                
    to_evaluate = [pt for pt in all_points if pt["point_id"] not in evaluated_ids]
    
    if args.limit_points > 0:
        to_evaluate = to_evaluate[:args.limit_points]
        
    print(f"[DHB] Campaign: {campaign_name}")
    print(f"[DHB] Total grid points: {len(all_points)}")
    print(f"[DHB] Already evaluated: {len(evaluated_ids)}")
    print(f"[DHB] To evaluate this run: {len(to_evaluate)}")
    
    if args.dry_run:
        print("[DHB] Dry-run enabled. Exiting.")
        return 0
        
    if not to_evaluate:
        print("[DHB] No points to evaluate. Updating plots and exiting.")
        if main_csv.exists():
            plot_existence_maps(main_csv, config, campaign_dir)
        return 0
        
    start_time = datetime.utcnow().isoformat()
    
    tmp_in = campaign_dir / "tmp_in.csv"
    tmp_out = campaign_dir / "tmp_out.csv"
    
    fields = ["point_id", "mH", "mA", "tan_beta", "lambda6", "M"]
    with open(tmp_in, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(to_evaluate)
        
    cmd = ["./build/bin/evaluate_point", str(tmp_in), str(tmp_out)]
    print(f"[DHB] Executing: {' '.join(cmd)}")
    
    start_ts = time.time()
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        print(f"[DHB][FAIL] evaluate_point failed with code {e.returncode}")
        return 1
        
    elapsed = time.time() - start_ts
    
    # Append to main_csv
    file_exists = main_csv.exists()
    with open(tmp_out, "r") as f_in, open(main_csv, "a", newline="") as f_out:
        if file_exists:
            next(f_in) # skip header
        for line in f_in:
            f_out.write(line)
            
    tmp_in.unlink()
    tmp_out.unlink()
    
    plot_existence_maps(main_csv, config, campaign_dir)
    
    end_time = datetime.utcnow().isoformat()
    
    manifest = {
        "campaign_name": campaign_name,
        "config": config,
        "git_commit": get_git_commit(),
        "hostname": os.uname().nodename,
        "start_time": start_time,
        "end_time": end_time,
        "command_line": sys.argv,
        "points_evaluated": len(to_evaluate),
        "total_points_in_csv": len(evaluated_ids) + len(to_evaluate),
        "elapsed_seconds": elapsed,
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"[DHB] Done! Evaluated {len(to_evaluate)} points in {elapsed:.2f}s.")
    print(f"[DHB] Campaign dir: {campaign_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
