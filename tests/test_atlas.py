import csv
import json
import math

from dhb import atlas, schema

BASE_ROW = {
    "point_id": "p1",
    "mh": "125.09",
    "mH": "300.0",
    "mA": "350.0",
    "mHp": "350.0",
    "tan_beta": "5.0",
    "set_param_phys_ok": "1",
    "positivity_ok": "1",
    "unitarity_ok": "1",
    "perturbativity_ok": "1",
    "stability_ok": "1",
    "theory_ok": "1",
    "rejection_stage": "none",
    "rejection_reason": "",
    "hb_allowed": "1",
    "hb_max_obsratio": "0.5",
    "hb_limiting_particle": "h2",
    "hb_limiting_process": "some_process",
    "hs_chi2": "101.0",
    "hs_nobs": "159",
    "hs_chi2_sm_ref": "100.0",
    "hs_delta_chi2": "1.0",
    "exp_ok": "1",
    "width_rel_diff_max": "0.001",
    "enrich_status": "ok",
    "total_width_H2": "1.0",
    "ctau_mm_H2": "1e-5",
    "br_gammagamma_H2": "0.001",
    "br_hh_H2": "0.4",
    "br_bb_H2": "0.3",
    "br_gg_H2": "0.2",
    "width_hh_H2": "0.4",
    "width_bb_H2": "0.3",
    "width_gg_H2": "0.2",
}


def make_row(**overrides):
    row = dict(BASE_ROW)
    row.update(overrides)
    return row


def settings():
    return dict(atlas.DEFAULT_SETTINGS)


# ---------------------------------------------------------------------------
# classify_row: region_class
# ---------------------------------------------------------------------------


def test_classify_row_allowed_low_signal():
    verdict = atlas.classify_row(make_row(), settings())
    assert verdict["region_class"] == "allowed_low_signal"
    assert verdict["is_theory_ok"] is True
    assert verdict["is_exp_ok"] is True
    assert verdict["is_allowed"] is True


def test_classify_row_theory_fail():
    row = make_row(theory_ok="0", rejection_stage="unitarity")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "theory_fail"
    assert verdict["is_theory_ok"] is False
    assert verdict["is_allowed"] is False


def test_classify_row_hbhs_not_run():
    row = make_row(enrich_status="skipped_theory_fail")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "hbhs_not_run"
    assert verdict["is_allowed"] is False


def test_classify_row_hb_excluded():
    row = make_row(hb_allowed="0", exp_ok="0")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "hb_excluded"
    assert verdict["is_allowed"] is False


def test_classify_row_hs_tension():
    row = make_row(hs_delta_chi2="12.0", exp_ok="0")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "hs_tension"
    assert verdict["is_allowed"] is False


def test_classify_row_exp_fail():
    # Synthetic: hb_allowed and hs_delta_chi2 both fine, but exp_ok says no.
    row = make_row(exp_ok="0")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "exp_fail"
    assert verdict["is_allowed"] is False


def test_classify_row_invalid_input_blank_theory_ok():
    row = make_row(theory_ok="")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "invalid_input"
    assert verdict["is_theory_ok"] is False
    assert verdict["is_allowed"] is False
    assert "theory_ok_not_0_or_1" in verdict["atlas_notes"]


def test_classify_row_invalid_input_garbage_theory_ok():
    row = make_row(theory_ok="maybe")
    verdict = atlas.classify_row(row, settings())
    assert verdict["region_class"] == "invalid_input"


# ---------------------------------------------------------------------------
# classify_row: candidate tags
# ---------------------------------------------------------------------------


def test_tags_require_is_allowed():
    # Same signal values as the base row, but not allowed -> no tags.
    row = make_row(theory_ok="0")
    verdict = atlas.classify_row(row, settings())
    assert verdict["is_allowed"] is False
    assert verdict["tag_hh_candidate"] is False
    assert verdict["tag_diphoton_candidate"] is False
    assert verdict["tag_displaced_candidate"] is False
    assert verdict["tag_prompt_candidate"] is False


def test_tag_hh_and_diphoton_candidate():
    verdict = atlas.classify_row(make_row(), settings())
    assert verdict["tag_hh_candidate"] is True
    assert verdict["tag_diphoton_candidate"] is True


def test_tag_prompt_candidate():
    row = make_row(ctau_mm_H2="1e-5")  # < ctau_prompt_max_mm (1e-3)
    verdict = atlas.classify_row(row, settings())
    assert verdict["tag_prompt_candidate"] is True
    assert verdict["tag_displaced_candidate"] is False


def test_tag_displaced_candidate():
    row = make_row(ctau_mm_H2="10.0")  # within [1e-3, 1e4]
    verdict = atlas.classify_row(row, settings())
    assert verdict["tag_displaced_candidate"] is True
    assert verdict["tag_prompt_candidate"] is False


def test_tag_missing_signal_columns_no_crash_no_tag():
    row = make_row(ctau_mm_H2="", br_gammagamma_H2="", br_hh_H2="")
    verdict = atlas.classify_row(row, settings())
    assert verdict["tag_hh_candidate"] is False
    assert verdict["tag_diphoton_candidate"] is False
    assert verdict["tag_displaced_candidate"] is False
    assert verdict["tag_prompt_candidate"] is False
    assert "missing_signal_columns_for_tags" in verdict["atlas_notes"]


# ---------------------------------------------------------------------------
# BR derivation
# ---------------------------------------------------------------------------


def test_plan_derived_signal_columns_derives_missing_brs():
    fieldnames = [
        "point_id",
        "total_width_H2",
        "width_hh_H2",
        "width_bb_H2",
        "width_gg_H2",
    ]
    derived, not_derivable = atlas.plan_derived_signal_columns(fieldnames)
    assert derived == ["br_bb_H2", "br_gg_H2", "br_hh_H2"]
    assert not_derivable == []


def test_plan_derived_signal_columns_not_derivable_without_total_width():
    fieldnames = ["point_id", "width_hh_H2"]
    derived, not_derivable = atlas.plan_derived_signal_columns(fieldnames)
    assert derived == []
    assert "br_hh_H2" in not_derivable


def test_plan_derived_signal_columns_skips_already_present():
    fieldnames = ["point_id", "total_width_H2", "width_hh_H2", "br_hh_H2"]
    derived, not_derivable = atlas.plan_derived_signal_columns(fieldnames)
    assert "br_hh_H2" not in derived
    assert "br_hh_H2" not in not_derivable


def test_derive_row_brs_computes_ratio():
    row = {"total_width_H2": "2.0", "width_hh_H2": "0.5"}
    result = atlas.derive_row_brs(row, ["br_hh_H2"])
    assert result["br_hh_H2"] == 0.25


def test_derive_row_brs_blank_on_zero_total_width():
    row = {"total_width_H2": "0.0", "width_hh_H2": "0.5"}
    result = atlas.derive_row_brs(row, ["br_hh_H2"])
    assert result["br_hh_H2"] == ""


def test_derive_row_brs_blank_on_missing_width():
    row = {"total_width_H2": "1.0"}
    result = atlas.derive_row_brs(row, ["br_hh_H2"])
    assert result["br_hh_H2"] == ""


# ---------------------------------------------------------------------------
# Full CLI (run) via tmp_path
# ---------------------------------------------------------------------------

FULL_FIELDS = list(BASE_ROW.keys())


def write_csv(path, rows, fieldnames=None):
    fieldnames = fieldnames or FULL_FIELDS
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def test_run_rows_not_dropped(tmp_path):
    rows = [
        make_row(point_id="p1"),
        make_row(point_id="p2", theory_ok="0"),
        make_row(point_id="p3", enrich_status="skipped_theory_fail"),
    ]
    input_csv = tmp_path / "hbhs_enriched.csv"
    write_csv(input_csv, rows)
    out_dir = tmp_path / "out"

    rc = atlas.run(["--input", str(input_csv), "--output-dir", str(out_dir)])
    assert rc == 0

    with open(out_dir / "boundary_atlas.csv", newline="") as fh:
        out_rows = list(csv.DictReader(fh))
    assert len(out_rows) == len(rows)
    assert [r["point_id"] for r in out_rows] == ["p1", "p2", "p3"]


def test_run_missing_optional_columns_do_not_fail(tmp_path):
    minimal_fields = atlas.REQUIRED_THEORY_COLUMNS + schema.ENRICHMENT_COLUMNS
    rows = [{k: BASE_ROW[k] for k in minimal_fields}]
    input_csv = tmp_path / "hbhs_enriched.csv"
    write_csv(input_csv, rows, fieldnames=minimal_fields)
    out_dir = tmp_path / "out"

    rc = atlas.run(["--input", str(input_csv), "--output-dir", str(out_dir)])
    assert rc == 0

    with open(out_dir / "boundary_atlas_summary.json") as fh:
        summary = json.load(fh)
    assert summary["n_total"] == 1
    assert "point_id" in summary["missing_optional_columns"]
    assert "br_hh_H2" in summary["missing_optional_columns"]


def test_run_missing_required_column_fails(tmp_path, capsys):
    fields = [f for f in FULL_FIELDS if f != "positivity_ok"]
    input_csv = tmp_path / "hbhs_enriched.csv"
    write_csv(input_csv, [make_row()], fieldnames=fields)
    out_dir = tmp_path / "out"

    rc = atlas.run(["--input", str(input_csv), "--output-dir", str(out_dir)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "[DHB][FAIL]" in captured.err
    assert not (out_dir / "boundary_atlas.csv").exists()


def test_run_summary_counts(tmp_path):
    rows = [
        make_row(point_id="p1"),  # allowed_low_signal
        make_row(point_id="p2", theory_ok="0"),  # theory_fail
        make_row(point_id="p3", hb_allowed="0", exp_ok="0"),  # hb_excluded
    ]
    input_csv = tmp_path / "hbhs_enriched.csv"
    write_csv(input_csv, rows)
    out_dir = tmp_path / "out"

    rc = atlas.run(["--input", str(input_csv), "--output-dir", str(out_dir)])
    assert rc == 0

    with open(out_dir / "boundary_atlas_summary.json") as fh:
        summary = json.load(fh)
    assert summary["n_total"] == 3
    assert summary["n_theory_ok"] == 2
    assert summary["n_allowed"] == 1
    assert summary["n_by_region_class"]["theory_fail"] == 1
    assert summary["n_by_region_class"]["hb_excluded"] == 1
    assert summary["n_by_region_class"]["allowed_low_signal"] == 1
    assert summary["n_hh_candidate"] == 1
    assert summary["atlas_schema_version"] == atlas.ATLAS_SCHEMA_VERSION


def test_run_manifest_creation(tmp_path):
    input_csv = tmp_path / "hbhs_enriched.csv"
    write_csv(input_csv, [make_row()])
    out_dir = tmp_path / "out"

    rc = atlas.run(["--input", str(input_csv), "--output-dir", str(out_dir)])
    assert rc == 0

    with open(out_dir / "boundary_atlas_manifest.json") as fh:
        manifest = json.load(fh)

    assert manifest["stage"] == "boundary_atlas"
    assert manifest["atlas_schema_version"] == atlas.ATLAS_SCHEMA_VERSION
    assert manifest["input"] == str(input_csv)
    assert manifest["row_counts"] == {"input": 1, "output": 1}
    assert "started_at_utc" in manifest and "finished_at_utc" in manifest
    assert "git_commit" in manifest
    assert isinstance(manifest["parquet_written"], bool)
    if not manifest["parquet_written"]:
        assert manifest["parquet_skipped_reason"]
