"""Machine-readable data contracts for the cross-stage CSV handoffs.

The historical v0 path remains supported:

    evaluate_point.csv -> hbhs_enriched.csv -> boundary_atlas.csv

The LLP-aware v1 path is additive:

    hbhs_enriched.csv -> llp_signal_enriched.csv -> boundary_atlas_v1.csv

Each contract is a plain mapping mirrored under ``contracts/*.yaml``.
``python -m dhb.contracts --emit contracts`` regenerates that mirror.
"""

import argparse
import os
import sys

from . import schema

HBAR_C_GEV_MM = 1.973269804e-13

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
    return {
        "name": "ctau_mm_H2 == hbar_c / total_width_H2",
        "output": "ctau_mm_H2",
        "numerator": HBAR_C_GEV_MM,
        "denominator": "total_width_H2",
        "rel_tol": 1e-6,
        "only_when_positive": "total_width_H2",
    }


THEORY = {
    "name": schema.THEORY_SCHEMA_VERSION,
    "produced_by": "src/evaluate_point.cpp",
    "consumed_by": "dhb.enrich",
    "file": "evaluate_point.csv",
    "required_columns": ["point_id", "theory_ok"] + list(schema.HBHS_BLOCK_COLUMNS),
    "full_columns": EVALUATE_POINT_FULL_COLUMNS,
    "invariants": [_ctau_invariant()],
    "aliases": {
        "ctau_mm_H2": ["ctau_mm"],
        "total_width_H2": ["total_width_GeV"],
    },
}

ENRICHED = {
    "name": schema.ENRICHED_SCHEMA_VERSION,
    "produced_by": "dhb.enrich",
    "consumed_by": "dhb.atlas",
    "file": "hbhs_enriched.csv",
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
    "full_columns": None,
    "invariants": [],
    "aliases": THEORY["aliases"],
}

LLP_SIGNAL = {
    "name": schema.LLP_SIGNAL_SCHEMA_VERSION,
    "produced_by": "dhb.llp_signal",
    "consumed_by": "dhb.atlas_v1",
    "file": "llp_signal_enriched.csv",
    "required_columns": list(schema.LLP_SIGNAL_NORMALIZED_INPUT_COLUMNS)
    + list(schema.LLP_SIGNAL_COLUMNS),
    "full_columns": None,
    "invariants": [],
    "aliases": {
        "m_H2_GeV": ["mH_input_GeV", "mH", "m_phi"],
        "g_hH2H2_GeV": [],
        "ctau_mm_H2": ["ctau_mm"],
        "br_bb_H2": ["br_bb"],
        "total_width_H2": ["total_width_GeV"],
        "width_bb_H2": ["width_bb_GeV"],
    },
}

ATLAS_V1 = {
    "name": schema.BOUNDARY_ATLAS_V1_SCHEMA_VERSION,
    "produced_by": "dhb.atlas_v1",
    "consumed_by": "downstream analysis / plotting / benchmark selection",
    "file": "boundary_atlas_v1.csv",
    "required_columns": [
        "region_class",
        "is_theory_ok",
        "is_exp_ok",
        "is_allowed",
        "is_signal_domain_supported",
        "is_signal_calibration_validated",
        "is_signal_at_or_above_S95",
    ],
    "full_columns": None,
    "invariants": [],
    "aliases": LLP_SIGNAL["aliases"],
}

CONTRACTS = {
    "evaluate_point_v1": THEORY,
    "hbhs_enriched_v1": ENRICHED,
    "boundary_atlas_v0": ATLAS,
    "llp_signal_enriched_v1": LLP_SIGNAL,
    "boundary_atlas_v1": ATLAS_V1,
}


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contracts_dir():
    return os.path.join(repo_root(), "contracts")


def _yaml_path(name):
    return os.path.join(contracts_dir(), name + ".yaml")


def emit(target_dir=None):
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
