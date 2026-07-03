"""Column schemas shared between the C++ evaluate_point stage and the
python HB/HS enrichment stage.

The HBHS block column list must stay in sync with write_hbhs_header() in
src/evaluate_point.cpp (schema evaluate_point_v1). Particle naming:
h1 = h (SM-like, CP-even), h2 = H (CP-even), h3 = A (CP-odd), hc = H+.
"""

import math

THEORY_SCHEMA_VERSION = "evaluate_point_v1"
ENRICHED_SCHEMA_VERSION = "hbhs_enriched_v1"

NEUTRALS = ("h1", "h2", "h3")
EFF_FERMIONS = ("ss", "cc", "bb", "tt", "mumu", "tautau")
EFF_BOSONS = ("WW", "ZZ", "Zga", "gaga", "gg")
HH_PAIRS = ("h1h1", "h2h2", "h3h3", "h1h2", "h1h3", "h2h3")
HC_DECAYS = ("cs", "cb", "tb", "taunu")

MASS_COLUMN = {"h1": "mh", "h2": "mH", "h3": "mA", "hc": "mHp"}
TOTAL_WIDTH_COLUMN = {
    "h1": "total_width_h1",
    "h2": "total_width_H2",
    "h3": "total_width_h3",
    "hc": "total_width_hc",
}


def hbhs_block_columns():
    """Columns appended by evaluate_point for the HB/HS enrichment stage,
    in the exact order written by the C++ evaluator."""
    cols = ["hbhs_block_ok"]
    for h in NEUTRALS:
        for f in EFF_FERMIONS:
            cols.append("eff_%s_%s_s" % (h, f))
            cols.append("eff_%s_%s_p" % (h, f))
        for b in EFF_BOSONS:
            cols.append("eff_%s_%s" % (h, b))
        for i in NEUTRALS:
            cols.append("eff_%s_%sZ" % (h, i))
    cols += ["total_width_h1", "total_width_h3", "total_width_hc"]
    for h in NEUTRALS:
        for p in HH_PAIRS:
            cols.append("br_%s_%s" % (h, p))
        for i in NEUTRALS:
            cols.append("br_%s_%sZ" % (h, i))
        cols.append("br_%s_hcW" % h)
    cols += [
        "br_t_hcb",
        "br_hc_cs",
        "br_hc_cb",
        "br_hc_tb",
        "br_hc_taunu",
        "br_hc_h1W",
        "br_hc_h2W",
        "br_hc_h3W",
        "hc_kappa_t",
        "hc_kappa_b",
    ]
    return cols


HBHS_BLOCK_COLUMNS = hbhs_block_columns()

# Columns appended by the enrichment stage, in output order.
ENRICHMENT_COLUMNS = [
    "hb_allowed",
    "hb_max_obsratio",
    "hb_limiting_particle",
    "hb_limiting_process",
    "hs_chi2",
    "hs_nobs",
    "hs_chi2_sm_ref",
    "hs_delta_chi2",
    "exp_ok",
    "width_rel_diff_max",
    "enrich_status",
]

ENRICH_STATUS_OK = "ok"
ENRICH_STATUS_SKIPPED = "skipped_theory_fail"


def parse_float(row, key):
    """Parse a CSV field as float; empty/invalid fields become NaN."""
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def parse_flag(row, key):
    """Parse a 0/1 CSV flag column."""
    return row.get(key, "").strip() == "1"


def missing_columns(fieldnames, required):
    present = set(fieldnames or [])
    return [c for c in required if c not in present]


def is_finite(value):
    return isinstance(value, float) and math.isfinite(value)
