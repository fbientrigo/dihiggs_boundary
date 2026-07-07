"""Machine-readable data contracts for the cross-stage CSV handoffs.

This module is the single source of truth for the column sets that cross a
stage boundary in the dihiggs_boundary pipeline:

    evaluate_point.csv  --(dhb.enrich)-->  hbhs_enriched.csv  --(dhb.atlas)-->  boundary_atlas.csv

Each contract is built from ``dhb.schema`` (and the evaluate_point theory
schema) so the column lists cannot silently drift from the code that reads and
writes these CSVs. The prose specs in ``docs/*_contract.md`` remain the human
description; this module is the enforceable mirror.

``python -m dhb.contracts --emit contracts`` regenerates the committed YAML
mirror under ``<repo>/contracts/``; ``tests/test_contracts.py`` asserts the
committed YAML still matches this code, so a change to one without the other
fails CI.
"""

import argparse
import os
import sys

from . import schema

# hbar*c used by the theory stage (src/evaluate_point.cpp) to derive
# ctau_mm_H2. Mirrors conventions/physics_conventions.yaml (hbar_c_gev_mm) and
# the value quoted in docs/evaluate_point_contract.md. Kept here so the
# ctau_mm_H2 invariant below can be checked without importing across repos.
HBAR_C_GEV_MM = 1.973269804e-13

# --- Theory stage: evaluate_point_v1 --------------------------------------
# The 47 non-HBHS columns emitted by src/evaluate_point.cpp, in order, per
# docs/evaluate_point_contract.md ("Required output columns"). The HBHS input
# block (schema.HBHS_BLOCK_COLUMNS) is appended after rejection_reason.
EVALUATE_POINT_THEORY_COLUMNS = [
    "point_id",
    "mh",
    "mH",
    "mA",
    "mHp",
    "tan_beta",
    "beta",
    "sin_ba",
    "lambda6_input",
    "lambda7_input",
    "M",
    "M2",
    "m12_sq_input",
    "M2_recomputed",
    "relative_M2_reconstruction_error",
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "triple_ok",
    "theory_ok",
    "lambda1",
    "lambda2",
    "lambda3",
    "lambda4",
    "lambda5",
    "lambda6_derived",
    "lambda7_derived",
    "m12_sq_derived",
    "tan_beta_derived",
    "width_bb_H2",
    "width_tautau_H2",
    "width_WW_H2",
    "width_ZZ_H2",
    "width_gammagamma_H2",
    "width_Zgamma_H2",
    "width_gg_H2",
    "width_hh_H2",
    "total_width_H2",
    "br_gammagamma_H2",
    "ctau_mm_H2",
    "yukawa_assignment",
    "scalar_z2_status",
    "soft_z2_only",
    "rejection_stage",
    "rejection_reason",
]

EVALUATE_POINT_FULL_COLUMNS = EVALUATE_POINT_THEORY_COLUMNS + list(
    schema.HBHS_BLOCK_COLUMNS
)


def _ctau_invariant():
    """ctau_mm_H2 must equal HBAR_C_GEV_MM / total_width_H2 (when the width is
    positive and finite). This is the same rule the theory stage applies when
    it derives the lifetime proxy; validating it at a boundary catches a CSV
    that was hand-edited or produced by a drifted evaluator."""
    return {
        "name": "ctau_mm_H2 == hbar_c / total_width_H2",
        "output": "ctau_mm_H2",
        "numerator": HBAR_C_GEV_MM,
        "denominator": "total_width_H2",
        "rel_tol": 1e-6,
        "only_when_positive": "total_width_H2",
    }


# A "contract" is a plain dict so it serialises straight to YAML/JSON and is
# trivial to diff. required_columns is what a *consumer* must be able to find;
# full_columns is everything the *producer* writes (for documentation).
THEORY = {
    "name": schema.THEORY_SCHEMA_VERSION,  # evaluate_point_v1
    "produced_by": "src/evaluate_point.cpp",
    "consumed_by": "dhb.enrich",
    "file": "evaluate_point.csv",
    "required_columns": ["point_id", "theory_ok"] + list(schema.HBHS_BLOCK_COLUMNS),
    "full_columns": EVALUATE_POINT_FULL_COLUMNS,
    "invariants": [_ctau_invariant()],
    "aliases": {
        # Cross-repo naming: dihiggs_hep_cross calls the same physical
        # quantity ctau_mm (no per-particle suffix). See the recast input
        # contract in that repo. They are the same number for the H2 scalar.
        "ctau_mm_H2": ["ctau_mm"],
        "total_width_H2": ["total_width_GeV"],
    },
}

ENRICHED = {
    "name": schema.ENRICHED_SCHEMA_VERSION,  # hbhs_enriched_v1
    "produced_by": "dhb.enrich",
    "consumed_by": "dhb.atlas",
    "file": "hbhs_enriched.csv",
    # dhb.atlas checks these when it opens the file.
    "required_columns": (
        [
            "set_param_phys_ok",
            "positivity_ok",
            "unitarity_ok",
            "perturbativity_ok",
            "stability_ok",
            "theory_ok",
            "rejection_stage",
            "rejection_reason",
        ]
        + list(schema.ENRICHMENT_COLUMNS)
    ),
    "full_columns": EVALUATE_POINT_FULL_COLUMNS + list(schema.ENRICHMENT_COLUMNS),
    "invariants": [_ctau_invariant()],
    "aliases": THEORY["aliases"],
}

ATLAS = {
    "name": "boundary_atlas_v0",
    "produced_by": "dhb.atlas",
    "consumed_by": "downstream analysis / plotting",
    "file": "boundary_atlas.csv",
    "required_columns": [
        "region_class",
        "is_theory_ok",
        "is_exp_ok",
        "is_allowed",
    ],
    "full_columns": None,  # depends on which optional signal columns were present
    "invariants": [],
    "aliases": THEORY["aliases"],
}

CONTRACTS = {
    "evaluate_point_v1": THEORY,
    "hbhs_enriched_v1": ENRICHED,
    "boundary_atlas_v0": ATLAS,
}


def repo_root():
    # python/dhb/contracts.py -> repo root is two levels up from python/.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contracts_dir():
    return os.path.join(repo_root(), "contracts")


def _yaml_path(name):
    return os.path.join(contracts_dir(), name + ".yaml")


def emit(target_dir=None):
    """Write each contract to <target_dir>/<name>.yaml. Returns the list of
    paths written."""
    import yaml

    target_dir = target_dir or contracts_dir()
    os.makedirs(target_dir, exist_ok=True)
    written = []
    for name, contract in CONTRACTS.items():
        path = os.path.join(target_dir, name + ".yaml")
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            yaml.safe_dump(contract, fh, sort_keys=False, default_flow_style=False)
        os.replace(tmp, path)
        written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit the CSV data contracts as YAML.")
    parser.add_argument(
        "--emit",
        nargs="?",
        const="",
        default="",
        help="directory to write <name>.yaml into (default: <repo>/contracts)",
    )
    args = parser.parse_args(argv)
    target = args.emit or contracts_dir()
    for path in emit(target):
        print("[DHB] wrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
