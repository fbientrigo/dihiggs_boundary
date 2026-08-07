import math

from dhb import point_fields


def test_resolve_canonical_dihiggs_point_v2_names_and_derive_br():
    row = {
        "mH_input_GeV": "150",
        "g_hH2H2_GeV": "63.5",
        "ctau_mm": "4.0",
        "width_bb_GeV": "0.75",
        "total_width_GeV": "1.0",
    }
    values, sources, issues = point_fields.resolve_signal_inputs(row)
    assert values["m_H2_GeV"] == 150.0
    assert values["g_hH2H2_GeV"] == 63.5
    assert values["ctau_mm_H2"] == 4.0
    assert values["br_bb_H2"] == 0.75
    assert sources["br_bb_H2"] == "width_bb_GeV/total_width_GeV"
    assert issues == []


def test_conflicting_mass_aliases_fail_closed():
    row = {
        "mH": "150",
        "mH_input_GeV": "151",
        "g_hH2H2_GeV": "1",
        "ctau_mm_H2": "1",
        "br_bb_H2": "0.5",
    }
    values, _sources, issues = point_fields.resolve_signal_inputs(row)
    assert math.isnan(values["m_H2_GeV"])
    assert any(item.startswith("conflicting_aliases:m_H2_GeV") for item in issues)


def test_direct_br_must_match_same_row_width_ratio():
    row = {
        "mH": "150",
        "g_hH2H2_GeV": "1",
        "ctau_mm_H2": "1",
        "br_bb_H2": "0.8",
        "width_bb_H2": "0.5",
        "total_width_H2": "1.0",
    }
    values, _sources, issues = point_fields.resolve_signal_inputs(row)
    assert math.isnan(values["br_bb_H2"])
    assert "conflicting_br_bb_and_width_ratio" in issues


def test_negative_g_is_not_accepted_as_magnitude():
    row = {
        "mH": "150",
        "g_hH2H2_GeV": "-1",
        "ctau_mm_H2": "1",
        "br_bb_H2": "0.5",
    }
    values, _sources, issues = point_fields.resolve_signal_inputs(row)
    assert math.isnan(values["g_hH2H2_GeV"])
    assert "invalid:g_hH2H2_GeV_must_be_nonnegative_magnitude" in issues
