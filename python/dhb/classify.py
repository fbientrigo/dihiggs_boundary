"""Classification of enriched points into experimentally allowed/excluded.

Thresholds come from the run config (configs/theory_atlas_v0.yaml,
experiment_higgstools block); raw HB/HS values are always stored so the
classification can be redone with different cuts without re-running.
"""

import math

# 2-sigma for the 2 effective parameters (hb boundary + hs chi2 direction)
# is not well defined a priori; the default matches the documented choice
# in configs/theory_atlas_v0.yaml (95% CL for 2 dof).
DEFAULT_HS_DELTA_CHI2_MAX = 6.18


def load_experiment_config(config_path):
    """Read the experiment_higgstools block from a run config yaml.
    Returns a dict with defaults filled in. Missing file or block is not an
    error: defaults apply."""
    settings = {
        "enabled": True,
        "hs_delta_chi2_max": DEFAULT_HS_DELTA_CHI2_MAX,
    }
    if not config_path:
        return settings
    try:
        import yaml
    except ImportError:
        return settings
    try:
        with open(config_path) as fh:
            config = yaml.safe_load(fh) or {}
    except OSError:
        return settings
    block = (config.get("evaluation") or {}).get("experiment_higgstools") or {}
    if "enabled" in block:
        settings["enabled"] = bool(block["enabled"])
    if "hs_delta_chi2_max" in block:
        settings["hs_delta_chi2_max"] = float(block["hs_delta_chi2_max"])
    return settings


def exp_ok(hb_allowed, hs_delta_chi2, hs_delta_chi2_max):
    """A point is experimentally allowed when HiggsBounds does not exclude
    it and its HiggsSignals chi2 is within the cut of the SM reference."""
    if not hb_allowed:
        return False
    if not (isinstance(hs_delta_chi2, float) and math.isfinite(hs_delta_chi2)):
        return False
    return hs_delta_chi2 <= hs_delta_chi2_max
