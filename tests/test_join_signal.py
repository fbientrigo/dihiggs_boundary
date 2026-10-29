import csv

import yaml

from dhb import join_signal


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
    points = [{"point_id": p, "m_H2_GeV": "150.0"} for p in ("p1", "p2", "p3")]
    for row in points:  # boundary points carry no sigma; a stale value must not survive the join
        row["sigma_production_fb"] = "123.0"
        row["sigma_production_unc_fb"] = "1.0"
    write_csv(tmp_path / "points.csv", points)
    return registry


def run(tmp_path, registry):
    out = tmp_path / "joined.csv"
    rc = join_signal.run(["--points", str(tmp_path / "points.csv"), "--registry", str(registry), "--output", str(out)])
    with out.open(newline="") as fh:
        return rc, {r["point_id"]: r for r in csv.DictReader(fh)}


def test_only_registered_valid_sigma_is_joined(tmp_path):
    rc, rows = run(tmp_path, setup(tmp_path, "results/sigma.csv"))
    assert rc == 0
    assert float(rows["p1"]["sigma_production_fb"]) == 4.0
    for pid in ("p2", "p3"):  # FAILED run, and no run at all
        assert rows[pid]["sigma_production_fb"] == ""


def test_no_registered_campaign_joins_nothing(tmp_path):
    rc, rows = run(tmp_path, setup(tmp_path, None))
    assert rc == 0
    assert all(r["sigma_production_fb"] == "" for r in rows.values())


def test_duplicate_point_id_in_sigma_table_fails(tmp_path):
    registry = setup(tmp_path, "results/sigma.csv")
    with (tmp_path / "results" / "sigma.csv").open("a", newline="") as fh:
        fh.write("p1,5.0,0.5,VALID\n")
    out = tmp_path / "joined.csv"
    assert join_signal.run(["--points", str(tmp_path / "points.csv"), "--registry", str(registry), "--output", str(out)]) == 2
    assert not out.exists()
