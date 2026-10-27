import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aggregate_adaptive_boundary.py"
SPEC = importlib.util.spec_from_file_location("adaptive_aggregate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_irregular_leaf_plot_includes_pending_rectangles(tmp_path):
    rows = [{"tan_beta": 100.0, "leaf_id": "a", "parent_id": "", "depth": 1, "active": True,
             "mphi_min_GeV": 130.0, "mphi_max_GeV": 185.0, "Mbar_min_GeV": 130.0, "Mbar_max_GeV": 185.0,
             "mphi_center_GeV": 157.5, "Mbar_center_GeV": 157.5, "coverage_state": "survivor_region", "seed_status": "not_applicable",
             "has_survivor": True, "profile_count": 16, "valid_count": 8, "theory_pass_fraction": .5,
             "max_abs_g_physical_hphiphi_GeV": 12.5, "dominant_rejection_stage": "", "dominant_rejection_reason": "", "best_point_id": "p"},
            {"tan_beta": 100.0, "leaf_id": "b", "parent_id": "", "depth": 0, "active": True,
             "mphi_min_GeV": 185.0, "mphi_max_GeV": 350.0, "Mbar_min_GeV": 130.0, "Mbar_max_GeV": 350.0,
             "mphi_center_GeV": 267.5, "Mbar_center_GeV": 240.0, "coverage_state": "pending_refinement", "seed_status": "survivor",
             "has_survivor": True, "profile_count": 64, "valid_count": 1, "theory_pass_fraction": 1 / 64,
             "max_abs_g_physical_hphiphi_GeV": 10.0, "dominant_rejection_stage": "", "dominant_rejection_reason": "", "best_point_id": "p"}]
    outputs = MODULE.make_plots(rows, tmp_path, 130, 350)
    assert all(Path(path).exists() for path in outputs.values())
