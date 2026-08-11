import csv
import json
import math
import sys
import types

from dhb import llp_calibration, llp_signal


def calibration(status="VALIDATED"):
    return llp_calibration.validate_calibration(
        {
            "schema_version": "dhb.llp_signal_calibration.v2",
            "calibration_version": "synthetic_test_v2",
            "calibration_status": status,
            "domain": {
                "m_H2_GeV": {"value": 150.0, "abs_tolerance": 1e-9},
                "ctau_min_mm": 1.0,
                "ctau_max_mm": 100.0,
            },
            "acceptance": {
                "analysis": "Trackless",
                "model": "log_linear_ctau",
                "points": [
                    {"ctau_mm": 1.0, "aeff": 0.1, "aeff_unc": 0.01},
                    {"ctau_mm": 10.0, "aeff": 0.2, "aeff_unc": 0.02},
                    {"ctau_mm": 100.0, "aeff": 0.1, "aeff_unc": 0.01},
                ],
            },
            "normalization": {"luminosity_fb": 139.0, "S95": 3.0},
            "classification": {"near_fraction": 0.2},
            "provenance": {"purpose": "unit_test_only"},
        }
    )


def base_row(**overrides):
    row = {
        "point_id": "p1",
        "mH": "150.0",
        "g_hH2H2_GeV": "10.0",
        "ctau_mm_H2": "10.0",
        "width_bb_H2": "0.5",
        "total_width_H2": "1.0",
        "sigma_production_fb": "4.0",
        "sigma_production_unc_fb": "0.4",
    }
    row.update(overrides)
    return row


def test_signal_arithmetic_applies_br_squared_once():
    out = llp_signal.evaluate_row(base_row(), calibration())
    assert out["br_bb_H2"] == 0.5
    assert out["sigma_production_fb"] == 4.0
    assert out["sigma_4b_fb"] == 1.0  # 4 * (0.5)^2
    assert out["Trackless_Aeff"] == 0.2
    assert out["sigma_visible_fb"] == 0.2
    assert math.isclose(out["N_expected"], 27.8)
    assert out["N_expected_139fb"] == out["N_expected"]
    assert math.isclose(out["N_over_S95"], 27.8 / 3.0)
    assert out["threshold_class"] == "ABOVE"
    assert out["signal_domain_status"] == llp_signal.DOMAIN_SUPPORTED
    assert out["signal_status"] == llp_signal.STATUS_COMPUTED_VALIDATED


def test_signal_uses_per_row_madgraph_cross_section_not_g_scaling():
    out = llp_signal.evaluate_row(
        base_row(
            g_hH2H2_GeV="20.0",
            sigma_production_fb="7.0",
            sigma_production_unc_fb="0.7",
        ),
        calibration(),
    )
    assert out["g_hH2H2_GeV"] == 20.0
    assert out["sigma_production_fb"] == 7.0
    assert out["sigma_production_unc_fb"] == 0.7


def test_missing_direct_production_preserves_row_but_no_signal():
    row = base_row()
    row.pop("sigma_production_fb")
    out = llp_signal.evaluate_row(row, calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_MISSING
    assert out["signal_status"] == llp_signal.STATUS_NOT_COMPUTED
    assert out["sigma_visible_fb"] == ""
    assert "missing:sigma_production_fb" in out["signal_notes"]


def test_missing_coupling_preserves_row_but_no_signal():
    row = base_row()
    row.pop("g_hH2H2_GeV")
    out = llp_signal.evaluate_row(row, calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_MISSING
    assert out["signal_status"] == llp_signal.STATUS_NOT_COMPUTED
    assert out["sigma_visible_fb"] == ""
    assert "missing:g_hH2H2_GeV" in out["signal_notes"]


def test_malformed_populated_alias_does_not_fall_back_to_width_derived_br():
    out = llp_signal.evaluate_row(base_row(br_bb_H2="not-a-number"), calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_MISSING
    assert out["signal_status"] == llp_signal.STATUS_NOT_COMPUTED
    assert "invalid:br_bb_H2" in out["signal_notes"]
    assert out["sigma_visible_fb"] == ""


def test_malformed_canonical_mass_does_not_fall_back_to_legacy_alias():
    out = llp_signal.evaluate_row(
        base_row(m_H2_GeV="not-a-number", mH="150.0"), calibration()
    )
    assert out["signal_domain_status"] == llp_signal.DOMAIN_MISSING
    assert "invalid:m_H2_GeV" in out["signal_notes"]


def test_mass_outside_recast_domain_keeps_madgraph_sigma_but_not_visible_signal():
    out = llp_signal.evaluate_row(base_row(mH="151.0"), calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_OUTSIDE
    assert out["sigma_production_fb"] == 4.0
    assert out["sigma_visible_fb"] == ""
    assert "mass_outside_calibration" in out["signal_notes"]


def test_ctau_interpolation_is_log_linear():
    cal = calibration()
    midpoint = math.sqrt(10.0)
    aeff, unc = llp_calibration.acceptance_response(cal, midpoint)
    assert math.isclose(aeff, 0.15)
    assert math.isclose(unc, 0.015)


def test_provisional_calibration_is_visible_in_signal_status():
    out = llp_signal.evaluate_row(base_row(), calibration(status="PROVISIONAL"))
    assert out["signal_domain_status"] == llp_signal.DOMAIN_SUPPORTED
    assert out["signal_status"] == llp_signal.STATUS_COMPUTED_PROVISIONAL
    assert out["signal_calibration_status"] == "PROVISIONAL"


def test_declared_domain_must_be_covered_by_acceptance_table():
    bad = {
        "schema_version": "dhb.llp_signal_calibration.v2",
        "calibration_version": "bad",
        "calibration_status": "PROVISIONAL",
        "domain": {
            "m_H2_GeV": {"value": 150.0, "abs_tolerance": 0.0},
            "ctau_min_mm": 0.1,
            "ctau_max_mm": 100.0,
        },
        "acceptance": {
            "analysis": "Trackless",
            "model": "log_linear_ctau",
            "points": [
                {"ctau_mm": 1.0, "aeff": 0.1},
                {"ctau_mm": 100.0, "aeff": 0.1},
            ],
        },
        "normalization": {"luminosity_fb": 139.0, "S95": 3.0},
        "classification": {"near_fraction": 0.2},
    }
    try:
        llp_calibration.validate_calibration(bad)
    except llp_calibration.CalibrationError:
        pass
    else:
        raise AssertionError("invalid domain coverage must fail")


def test_yaml_syntax_error_writes_failure_marked_rows_and_manifest(tmp_path, monkeypatch):
    class FakeYAMLError(Exception):
        pass

    def bad_safe_load(_):
        raise FakeYAMLError("unclosed collection")

    monkeypatch.setitem(
        sys.modules,
        "yaml",
        types.SimpleNamespace(YAMLError=FakeYAMLError, safe_load=bad_safe_load),
    )
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "llp_signal_enriched.csv"
    calibration_path = tmp_path / "broken.yaml"
    calibration_path.write_text("schema_version: [unclosed\n")
    with input_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sorted(base_row()))
        writer.writeheader()
        writer.writerow(base_row())

    assert llp_signal.run(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--calibration",
            str(calibration_path),
        ]
    ) == 2

    with output_path.open(newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["signal_domain_status"] == llp_signal.DOMAIN_INVALID_CALIBRATION
    assert row["signal_status"] == llp_signal.STATUS_NOT_COMPUTED
    manifest = json.loads((tmp_path / "llp_signal_manifest.json").read_text())
    assert manifest["calibration_valid"] is False
    assert "invalid YAML calibration" in manifest["calibration_error"]
