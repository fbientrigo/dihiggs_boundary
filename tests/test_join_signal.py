import csv
import math

import yaml

from dhb import join_signal, llp_signal
from test_llp_signal import base_row, calibration


def write_csv(path, rows):
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def setup(tmp_path, authoritative_results):
    """Fake hep_cross repo (state/ + results/) and boundary points p1, p2, p3."""
    (tmp_path / "state").mkdir()
    (tmp_path / "results").mkdir()
    registry = tmp_path / "state" / "CURRENT_CAMPAIGN.yaml"
    registry.write_text(yaml.safe_dump({"madgraph": {"authoritative_results": authoritative_results}}))
    write_csv(tmp_path / "results" / "sigma.csv", [
        {"point_id": "p1", "sigma_production_fb": "4.0", "sigma_production_unc_fb": "0.4", "madgraph_status": "VALID"},
        {"point_id": "p2", "sigma_production_fb": "9.0", "sigma_production_unc_fb": "0.9", "madgraph_status": "FAILED"},
    ])
    points = [base_row(point_id=p) for p in ("p1", "p2", "p3")]
    for row in points:  # boundary points carry no sigma; a stale value must not survive the join
        row["sigma_production_fb"] = "123.0"
        row["sigma_production_unc_fb"] = "1.0"
    write_csv(tmp_path / "points.csv", points)
    cal = tmp_path / "cal.yaml"
    cal.write_text(yaml.safe_dump({
        "schema_version": "dhb.llp_signal_calibration.v2", "calibration_version": "t", "calibration_status": "VALIDATED",
        "domain": {"m_H2_GeV": {"value": 150.0, "abs_tolerance": 1e-9}, "ctau_min_mm": 1.0, "ctau_max_mm": 100.0},
        "acceptance": {"analysis": "Trackless", "model": "log_linear_ctau", "points": [
            {"ctau_mm": 1.0, "aeff": 0.1, "aeff_unc": 0.01}, {"ctau_mm": 10.0, "aeff": 0.2, "aeff_unc": 0.02},
            {"ctau_mm": 100.0, "aeff": 0.1, "aeff_unc": 0.01}]},
        "normalization": {"luminosity_fb": 139.0, "S95": 3.0}, "classification": {"near_fraction": 0.2},
    }))
    return registry, cal


def run(tmp_path, registry, cal):
    out = tmp_path / "llp_signal_enriched.csv"
    rc = join_signal.run(["--points", str(tmp_path / "points.csv"), "--registry", str(registry),
                          "--calibration", str(cal), "--output", str(out)])
    with out.open(newline="") as fh:
        return rc, {r["point_id"]: r for r in csv.DictReader(fh)}


def test_only_registered_valid_sigma_is_joined(tmp_path):
    registry, cal = setup(tmp_path, "results/sigma.csv")
    rc, rows = run(tmp_path, registry, cal)
    assert rc == 0
    assert float(rows["p1"]["sigma_production_fb"]) == 4.0
    expected = llp_signal.evaluate_row(base_row(), calibration())
    assert math.isclose(float(rows["p1"]["N_expected"]), expected["N_expected"])
    for pid in ("p2", "p3"):  # FAILED run, and no run at all
        assert rows[pid]["sigma_production_fb"] == ""
        assert rows[pid]["signal_domain_status"] == llp_signal.DOMAIN_MISSING


def test_no_registered_campaign_joins_nothing(tmp_path):
    registry, cal = setup(tmp_path, None)
    rc, rows = run(tmp_path, registry, cal)
    assert rc == 0
    assert all(r["sigma_production_fb"] == "" for r in rows.values())


def test_duplicate_point_id_in_sigma_table_fails(tmp_path):
    registry, cal = setup(tmp_path, "results/sigma.csv")
    with (tmp_path / "results" / "sigma.csv").open("a", newline="") as fh:
        fh.write("p1,5.0,0.5,VALID\n")
    out = tmp_path / "llp_signal_enriched.csv"
    assert join_signal.run(["--points", str(tmp_path / "points.csv"), "--registry", str(registry),
                            "--calibration", str(cal), "--output", str(out)]) == 2
    assert not out.exists()
