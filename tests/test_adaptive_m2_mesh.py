from dhb.adaptive_m2_mesh import (
    _annotate_seed, budgeted_targets, children, eligible_refinement_targets, refinement_targets, root_index,
    root_leaves,
)


def _row(tb, x, y, ok):
    return {"tan_beta_input": str(tb), "mH_input_GeV": str(x), "M_plot_GeV": str(y),
            "theory_ok_v1": "1" if ok else "0", "rejection_stage": "none", "rejection_reason": ""}


def test_root_assignment_and_seed_classification():
    leaves = root_leaves([100.0], 130, 350, 10)
    rows = _annotate_seed([_row(100, 130, 130, True), _row(100, 350, 350, False)], leaves, 130, 350, 10)
    assert root_index(350, 130, 350, 10) == 9
    assert rows[0]["mesh_leaf_id"] == "tb_1e02_d00_x000_y000"
    assert next(leaf for leaf in leaves if leaf["ix"] == leaf["iy"] == 0)["coverage_state"] == "seed_survivor"
    assert next(leaf for leaf in leaves if leaf["ix"] == leaf["iy"] == 9)["coverage_state"] == "seed_tested_empty"


def test_survivor_halo_refines_only_adjacent_cells():
    leaves = root_leaves([100.0], 130, 350, 3)
    survivor = next(leaf for leaf in leaves if leaf["ix"] == leaf["iy"] == 0); survivor["has_survivor"] = True
    targets = refinement_targets(leaves, 0)
    assert {(leaf["ix"], leaf["iy"]) for leaf in targets} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    made = children(survivor, 130, 350, 3)
    assert len(made) == 4 and survivor["active"] is False
    assert next(leaf for leaf in leaves if leaf["ix"] == leaf["iy"] == 2)["active"] is True


def test_depth_budget_stop_keeps_pending_leaf_grey_state():
    leaves = root_leaves([100.0], 130, 350, 2)
    leaves[0]["has_survivor"] = True
    targets = refinement_targets(leaves, 0)
    selected, pending = budgeted_targets(targets, existing_rows=0, cap=64, proposals=16)
    assert len(selected) == 1 and pending
    for leaf in pending:
        leaf["coverage_state"] = "pending_refinement"
    assert all(leaf["coverage_state"] == "pending_refinement" for leaf in pending)
    assert eligible_refinement_targets(leaves, 6, max_depth=6) == []
