import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

HEADER = [
    "point_id",
    "mH",
    "mA",
    "tan_beta",
    "lambda6_input",
    "M",
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "triple_ok",
    "theory_ok",
    "stu_ok",
    "physics_ok",
    "rejection_stage",
]


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_batch(campaign_dir, batch_number, rows):
    batch_id = f"batch_{batch_number:06d}"
    batch_dir = campaign_dir / "batches" / batch_id
    batch_dir.mkdir(parents=True)

    write_csv(batch_dir / "evaluate_point.csv", HEADER, rows)
    point_header = ["point_id", "mH", "mA", "tan_beta", "lambda6", "M"]
    point_rows = [
        {
            "point_id": row["point_id"],
            "mH": row["mH"],
            "mA": row["mA"],
            "tan_beta": row["tan_beta"],
            "lambda6": row["lambda6_input"],
            "M": row["M"],
        }
        for row in rows
    ]
    write_csv(batch_dir / "points.csv", point_header, point_rows)

    manifest = {
        "campaign_id": campaign_dir.name,
        "batch_id": batch_id,
        "batch_number": batch_number,
        "input_rows": len(rows),
        "output_rows": len(rows),
        "batch_seed": 1000 + batch_number,
        "expected_z2_warning_count": 0,
        "filtered_z2_warning_count": 0,
        "status": "success",
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (batch_dir / "evaluate_point.log.raw").write_text("", encoding="utf-8")
    (batch_dir / "evaluate_point.log").write_text("", encoding="utf-8")
    (batch_dir / "DONE").write_text("", encoding="utf-8")


def make_row(point_id, mH, mA, tan_beta, lambda6_input, M, theory_ok, rejection_stage):
    theory = str(theory_ok)
    return {
        "point_id": point_id,
        "mH": str(mH),
        "mA": str(mA),
        "tan_beta": str(tan_beta),
        "lambda6_input": str(lambda6_input),
        "M": str(M),
        "set_param_phys_ok": "1",
        "positivity_ok": theory,
        "unitarity_ok": theory,
        "perturbativity_ok": theory,
        "stability_ok": theory,
        "triple_ok": theory,
        "theory_ok": theory,
        "stu_ok": theory,
        "physics_ok": theory,
        "rejection_stage": rejection_stage,
    }


def create_campaign(tmp_path):
    campaign_dir = tmp_path / "campaign"
    (campaign_dir / "batches").mkdir(parents=True)

    row_a = make_row("p1", 300.0, 310.0, 2.0, 0.10, 320.0, 1, "none")
    row_b = make_row("p2", 340.0, 350.0, 3.0, 0.20, 360.0, 0, "positivity")
    row_c = make_row("p2", 380.0, 390.0, 4.0, 0.30, 400.0, 1, "none")
    row_d = make_row("p4", 300.0, 310.0, 2.0, 0.10, 320.0, 1, "none")

    write_batch(campaign_dir, 1, [row_a, row_b])
    write_batch(campaign_dir, 2, [row_c, row_d])
    return campaign_dir


def run_script(*args, env=None):
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )


def count_data_rows(path):
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        return sum(1 for row in reader if row)


def test_rebuild_campaign_index_streaming_outputs(tmp_path):
    campaign_dir = create_campaign(tmp_path)

    run_script(
        "scripts/rebuild_campaign_index.py",
        "--campaign-dir",
        str(campaign_dir),
        "--progress-every",
        "1",
    )

    index_dir = campaign_dir / "index"
    expected_files = [
        "all_evaluate_point.csv",
        "point_hashes.txt",
        "rejection_counts.csv",
        "theory_acceptance_summary.csv",
        "campaign_summary.md",
    ]
    for filename in expected_files:
        assert (index_dir / filename).exists()

    assert count_data_rows(index_dir / "all_evaluate_point.csv") == 4

    with (index_dir / "theory_acceptance_summary.csv").open("r", newline="", encoding="utf-8") as f:
        summary = {row["metric"]: row for row in csv.DictReader(f)}
    assert summary["total_points"]["count"] == "4"
    assert summary["theory_ok"]["count"] == "3"
    assert summary["theory_ok"]["fraction"] == "0.75"

    summary_md = (index_dir / "campaign_summary.md").read_text(encoding="utf-8")
    assert "- **Duplicate point_id Count**: `1`" in summary_md
    assert "- **Duplicate point_hash Count**: `1`" in summary_md


def test_plot_campaign_pixels_streaming_outputs(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("numpy")

    campaign_dir = create_campaign(tmp_path)
    run_script("scripts/rebuild_campaign_index.py", "--campaign-dir", str(campaign_dir))

    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    run_script(
        "scripts/plot_campaign_pixels.py",
        "--campaign-dir",
        str(campaign_dir),
        "--bins",
        "4",
        "--progress-every-rows",
        "1",
        env=env,
    )

    outdir = campaign_dir / "plots" / "pixel_plots"
    expected_csvs = [
        "pixel_acceptance_mH_vs_M.csv",
        "pixel_acceptance_mH_vs_lambda6_input.csv",
        "pixel_acceptance_M_vs_lambda6_input.csv",
        "pixel_acceptance_tan_beta_vs_lambda6_input.csv",
        "pixel_acceptance_mH_vs_tan_beta.csv",
        "pixel_acceptance_mH_vs_mA.csv",
    ]
    for filename in expected_csvs:
        assert (outdir / filename).exists()
