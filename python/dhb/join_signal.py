"""Join hep_cross production sigma onto boundary points.

Keyed on point_id:
  boundary points CSV
  + the sigma table registered in hep_cross state/CURRENT_CAMPAIGN.yaml
    (madgraph.authoritative_results, a CSV path relative to the hep_cross repo)

Sigma comes from the registry only: there is no --sigma argument, so an
unregistered MadGraph run cannot be joined.  With no registered result
(authoritative_results: null) every row keeps blank sigma columns.  Only rows
with madgraph_status == VALID are joined; a duplicated point_id in the sigma
table is an error.
"""

import argparse
import csv
import os
import sys

import yaml

SIGMA_COLUMNS = ("sigma_production_fb", "sigma_production_unc_fb")


class JoinError(ValueError):
    pass


def registered_sigma_table(registry_path):
    """Return the absolute path of the registered sigma CSV, or None."""
    with open(registry_path) as fh:
        registry = yaml.safe_load(fh) or {}
    rel = (registry.get("madgraph") or {}).get("authoritative_results")
    if not rel:
        return None
    hep_cross_root = os.path.dirname(os.path.dirname(os.path.abspath(registry_path)))
    path = os.path.join(hep_cross_root, rel)
    if not os.path.isfile(path):
        raise JoinError("registered sigma table not found: %s" % path)
    return path


def load_sigma(path):
    sigma = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("madgraph_status") != "VALID":
                continue
            pid = row["point_id"]
            if pid in sigma:
                raise JoinError("duplicate point_id in sigma table: %s" % pid)
            sigma[pid] = {c: row[c] for c in SIGMA_COLUMNS}
    return sigma


def join(points_path, registry_path, out_path):
    """Write points + registered sigma columns to out_path. Returns (n_rows, n_joined)."""
    table = registered_sigma_table(registry_path)
    sigma = load_sigma(table) if table else {}
    with open(points_path, newline="") as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in reader.fieldnames if f not in SIGMA_COLUMNS] + list(SIGMA_COLUMNS)
        rows = list(reader)
    n_joined = 0
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            hit = sigma.get(row["point_id"], dict.fromkeys(SIGMA_COLUMNS, ""))
            n_joined += bool(hit["sigma_production_fb"])
            row.update(hit)  # never keep a sigma that did not come from the registry
            writer.writerow(row)
    return len(rows), n_joined


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--points", required=True, help="boundary points CSV (point_id + model/HBHS columns)")
    parser.add_argument("--registry", required=True, help="dihiggs_hep_cross/state/CURRENT_CAMPAIGN.yaml")
    parser.add_argument("--output", required=True, help="points + sigma CSV to write")
    args = parser.parse_args(argv)

    try:
        n_rows, n_joined = join(args.points, args.registry, args.output)
    except (OSError, JoinError, KeyError) as exc:
        print("[DHB][FAIL] join: %s" % exc, file=sys.stderr)
        return 2
    print("[DHB] joined registered sigma onto %d/%d points -> %s" % (n_joined, n_rows, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(run())
