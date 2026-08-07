import math

from dhb import llp_calibration, llp_signal


def calibration(status="VALIDATED"):
    return llp_calibration.validate_calibration(
        {
            "schema_version": "dhb.llp_signal_calibration.v1",
            "calibration_version": "synthetic_test_v1",
            "calibration_status": status,
            "domain": {
                "m_H2_GeV": {"value": 150.0, "abs_tolerance": 1e-9},
                "ctau_min_mm": 1.0,
                "ctau_max_mm": 100.0,
            },
            "production": {
                "model": "quadratic_anchor",
                "anchor_g_GeV": 10.0,
                "anchor_sigma_fb": 4.0,
                "anchor_sigma_unc_fb": 0.4,
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


def test_production_response_scales_quadratically_in_g():
    out = llp_signal.evaluate_row(base_row(g_hH2H2_GeV="20.0"), calibration())
    assert out["sigma_production_fb"] == 16.0
    assert out["sigma_production_unc_fb"] == 1.6


def test_missing_coupling_preserves_row_but_no_signal():
    row = base_row()
    row.pop("g_hH2H2_GeV")
    out = llp_signal.evaluate_row(row, calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_MISSING
    assert out["signal_status"] == llp_signal.STATUS_NOT_COMPUTED
    assert out["sigma_visible_fb"] == ""
    assert "missing:g_hH2H2_GeV" in out["signal_notes"]


def test_mass_outside_recast_domain_does_not_extrapolate():
    out = llp_signal.evaluate_row(base_row(mH="151.0"), calibration())
    assert out["signal_domain_status"] == llp_signal.DOMAIN_OUTSIDE
    assert out["sigma_production_fb"] == ""
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
        "schema_version": "dhb.llp_signal_calibration.v1",
        "calibration_version": "bad",
        "calibration_status": "PROVISIONAL",
        "domain": {
            "m_H2_GeV": {"value": 150.0, "abs_tolerance": 0.0},
            "ctau_min_mm": 0.1,
            "ctau_max_mm": 100.0,
        },
        "production": {
            "model": "quadratic_anchor",
            "anchor_g_GeV": 10.0,
            "anchor_sigma_fb": 1.0,
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
