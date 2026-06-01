import argparse
import csv
import math
import random

def generate_lhs(n_points, dims, seed):
    random.seed(seed)
    
    samples = {dim: [] for dim in dims}
    
    for dim_name, info in dims.items():
        is_log = info['log']
        min_val = info['min']
        max_val = info['max']
        
        if is_log:
            min_val = math.log10(min_val)
            max_val = math.log10(max_val)
            
        points = []
        for i in range(n_points):
            u = random.uniform(i / n_points, (i + 1) / n_points)
            val = min_val + u * (max_val - min_val)
            if is_log:
                val = 10 ** val
            points.append(val)
            
        random.shuffle(points)
        samples[dim_name] = points
        
    return samples

def main():
    parser = argparse.ArgumentParser(description="Generate Latin Hypercube boundary points")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    parser.add_argument("--n-points", type=int, default=5000, help="Number of points to generate")
    parser.add_argument("--seed", type=int, default=12345, help="Random seed")
    args = parser.parse_args()

    dims = {
        'mH': {'min': 240, 'max': 360, 'log': False},
        'mA': {'min': 280, 'max': 650, 'log': False},
        'tan_beta': {'min': 10, 'max': 10000, 'log': True},
        'lambda6': {'min': 1e-12, 'max': 1e-2, 'log': True},
        'M': {'min': 200, 'max': 450, 'log': False},
    }

    samples = generate_lhs(args.n_points, dims, args.seed)

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["point_id", "mH", "mA", "tan_beta", "lambda6", "M"])
        for i in range(args.n_points):
            point_id = f"lhs_{i:06d}"
            writer.writerow([
                point_id,
                samples['mH'][i],
                samples['mA'][i],
                samples['tan_beta'][i],
                samples['lambda6'][i],
                samples['M'][i]
            ])

    print(f"Generated {args.n_points} Latin Hypercube points to {args.output}")

if __name__ == "__main__":
    main()
