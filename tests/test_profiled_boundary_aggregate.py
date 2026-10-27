import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_profiled_boundary.py"


def test_aggregate_profiled_canonical_rows_and_plot_states(tmp_path):
    fields = [
        "point_id", "mh_input_GeV", "mH_input_GeV", "mA_input_GeV", "mHp_input_GeV",
        "sin_beta_minus_alpha_input", "tan_beta_input", "M2_input_GeV2", "lambda6_input",
        "lambda7_input", "construction_ok", "numerical_ok", "theory_ok_v1", "rejection_stage",
        "rejection_reason", "g_physical_hphiphi_GeV", "g_hH2H2_GeV",
    ]
    raw = tmp_path / "raw.csv"
    rows = []
    for tb in (100.0, 1e4, 1e5, 1e7):
        for mphi, mplot, survivor in ((130.0, 130.0, True), (130.0, 150.0, False)):
            for proposal in range(2):
                ok = survivor and proposal == 0
                rows.append({
                    "point_id": "p_%g_%g_%g_%d" % (tb, mphi, mplot, proposal), "mh_input_GeV": "125.13",
                    "mH_input_GeV": str(mphi), "mA_input_GeV": "300", "mHp_input_GeV": "300",
                    "sin_beta_minus_alpha_input": "1", "tan_beta_input": str(tb), "M2_input_GeV2": str(mplot * mplot),
                    "lambda6_input": "1e-6", "lambda7_input": "0", "construction_ok": "1", "numerical_ok": "1",
                    "theory_ok_v1": "1" if ok else "0", "rejection_stage": "none" if ok else "unitarity",
                    "rejection_reason": "ok" if ok else "failed", "g_physical_hphiphi_GeV": "-12.5" if ok else "nan",
                    "g_hH2H2_GeV": "12.5" if ok else "nan",
                })
    with raw.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    output = tmp_path / "out"
    subprocess.run([sys.executable, str(SCRIPT), "--input", str(raw), "--output-dir", str(output), "--expected-attempts", "2"], check=True)
    with (output / "aggregate_profiled_boundary.csv").open(newline="") as handle:
        aggregate = list(csv.DictReader(handle))
    assert len(aggregate) == 8
    survivor = next(row for row in aggregate if row["exists_theory_survivor"] == "1")
    assert survivor["max_abs_g_physical_hphiphi_GeV"] == "12.5"
    assert survivor["best_signed_g_physical_hphiphi_GeV"] == "-12.5"
    assert {row["coverage_class"] for row in aggregate} == {"survivor_region", "no_survivor_found"}
    assert (output / "figure1_boundary_rigidity.png").exists()
    assert (output / "figure2_max_physical_coupling.svg").exists()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["row_counts"] == {"raw": 16, "aggregate_outer_cells": 8, "theory_survivor_cells": 4}
