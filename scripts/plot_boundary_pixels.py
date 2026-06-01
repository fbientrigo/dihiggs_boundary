import argparse
import csv
import math
import os
import sys

try:
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

def main():
    parser = argparse.ArgumentParser(description="Plot boundary pixels (heatmaps)")
    parser.add_argument("--input", required=True, help="Input evaluate_point.csv file")
    parser.add_argument("--outdir", required=True, help="Output directory for plots and CSVs")
    parser.add_argument("--bins", type=int, default=64, help="Number of bins per axis")
    args = parser.parse_args()

    if not MATPLOTLIB_AVAILABLE:
        print("ERROR: matplotlib or numpy not available. Cannot generate plots.")
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)

    data = {
        'mH': [], 'mA': [], 'M': [], 'tan_beta': [], 'lambda6_input': [], 'theory_ok': []
    }

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data['mH'].append(float(row['mH']))
            data['mA'].append(float(row['mA']))
            data['M'].append(float(row['M']))
            data['tan_beta'].append(float(row['tan_beta']))
            data['lambda6_input'].append(float(row['lambda6_input']))
            data['theory_ok'].append(1 if row['theory_ok'] == '1' else 0)

    for k in data:
        data[k] = np.array(data[k])

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

        if x_is_log:
            x_data_plot = np.log10(x_data)
        else:
            x_data_plot = x_data
            
        if y_is_log:
            y_data_plot = np.log10(y_data)
        else:
            y_data_plot = y_data

        x_min, x_max = np.min(x_data_plot), np.max(x_data_plot)
        y_min, y_max = np.min(y_data_plot), np.max(y_data_plot)
        
        # Add a tiny padding to avoid exact edge issues where points land outside bins
        eps = 1e-9
        x_edges = np.linspace(x_min - eps, x_max + eps, args.bins + 1)
        y_edges = np.linspace(y_min - eps, y_max + eps, args.bins + 1)

        total_counts, _, _ = np.histogram2d(x_data_plot, y_data_plot, bins=[x_edges, y_edges])
        ok_counts, _, _ = np.histogram2d(x_data_plot[theory_ok == 1], y_data_plot[theory_ok == 1], bins=[x_edges, y_edges])

        # Plot density
        plt.figure(figsize=(8, 6))
        plt.pcolormesh(x_edges, y_edges, total_counts.T, cmap='Blues')
        plt.colorbar(label='Total counts')
        plt.xlabel(f"log10({x_var})" if x_is_log else x_var)
        plt.ylabel(f"log10({y_var})" if y_is_log else y_var)
        plt.title(f"Density: {y_var} vs {x_var}")
        plt.savefig(os.path.join(args.outdir, f"density_{x_var}_vs_{y_var}.png"), dpi=150)
        plt.close()

        # Plot acceptance fraction
        fraction = np.zeros_like(total_counts)
        mask = total_counts > 0
        fraction[mask] = ok_counts[mask] / total_counts[mask]
        
        fraction_masked = np.ma.masked_where(total_counts == 0, fraction)

        plt.figure(figsize=(8, 6))
        plt.pcolormesh(x_edges, y_edges, fraction_masked.T, cmap='viridis', vmin=0, vmax=1)
        plt.colorbar(label='Theory OK fraction')
        plt.xlabel(f"log10({x_var})" if x_is_log else x_var)
        plt.ylabel(f"log10({y_var})" if y_is_log else y_var)
        plt.title(f"Acceptance: {y_var} vs {x_var}")
        plt.savefig(os.path.join(args.outdir, f"acceptance_{x_var}_vs_{y_var}.png"), dpi=150)
        plt.close()

        # Save binned CSV
        csv_path = os.path.join(args.outdir, f"pixel_acceptance_{x_var}_vs_{y_var}.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow([x_var + "_bin_center", y_var + "_bin_center", "total_count", "theory_ok_count", "theory_ok_fraction"])
            for i in range(args.bins):
                for j in range(args.bins):
                    c = total_counts[i, j]
                    if c > 0:
                        xc = (x_edges[i] + x_edges[i+1]) / 2
                        yc = (y_edges[j] + y_edges[j+1]) / 2
                        if x_is_log: xc = 10**xc
                        if y_is_log: yc = 10**yc
                        ok = ok_counts[i, j]
                        frac = ok / c
                        writer.writerow([xc, yc, int(c), int(ok), frac])

    print(f"Saved pixel plots to {args.outdir}")

if __name__ == "__main__":
    main()
