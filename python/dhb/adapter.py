"""Translate one evaluate_point CSV row into a Higgs.predictions.Predictions.

The row must carry the HBHS input block (hbhs_block_ok == 1), i.e. the
SM-normalized effective couplings and non-SM branching ratios computed by
the C++ evaluator with 2HDMC conventions (see docs/hbhs_contract.md).

The Higgs.predictions module is passed in as an argument (HP) so the
translation logic is unit-testable without an installed HiggsTools.
"""

import math

from . import schema

# CP assignment of the neutral states in the CP-conserving 2HDM.
CP_ASSIGNMENT = {"h1": "even", "h2": "even", "h3": "odd"}

# Pair-decay column suffix -> daughter particle ids.
HH_PAIR_DAUGHTERS = {
    "h1h1": ("h1", "h1"),
    "h2h2": ("h2", "h2"),
    "h3h3": ("h3", "h3"),
    "h1h2": ("h1", "h2"),
    "h1h3": ("h1", "h3"),
    "h2h3": ("h2", "h3"),
}


def neutral_eff_couplings(row, name, HP):
    """Assemble NeutralEffectiveCouplings for neutral state `name`.

    Fermionic couplings are complex: CP-even part from the *_s column,
    CP-odd part from the *_p column. The evaluator only exports second and
    third generation couplings; in a Type-I 2HDM all up-type (down-type,
    charged-lepton) couplings are generation-universal, so the first
    generation reuses the second (uu:=cc, dd:=ss, ee:=mumu).

    kappa_lambda is only meaningful for the SM-like h1, where the exact
    alignment limit of the model contract makes it SM-like (lam=1).
    """

    def f(suffix):
        return schema.parse_float(row, "eff_%s_%s" % (name, suffix))

    def c(fermion):
        return complex(f(fermion + "_s"), f(fermion + "_p"))

    return HP.NeutralEffectiveCouplings(
        uu=c("cc"),
        dd=c("ss"),
        cc=c("cc"),
        ss=c("ss"),
        tt=c("tt"),
        bb=c("bb"),
        ee=c("mumu"),
        mumu=c("mumu"),
        tautau=c("tautau"),
        WW=f("WW"),
        ZZ=f("ZZ"),
        Zgam=f("Zga"),
        gamgam=f("gaga"),
        gg=f("gg"),
        lam=1.0 if name == "h1" else 0.0,
    )


def _add_neutral_bsm_decays(particle, row, name):
    """Add decays into BSM particles (hh pairs, hZ, H+W) as partial widths
    on top of the SM channels set by effectiveCouplingInput."""
    total_width = schema.parse_float(row, schema.TOTAL_WIDTH_COLUMN[name])
    if not (schema.is_finite(total_width) and total_width > 0.0):
        return
    for pair, (d1, d2) in HH_PAIR_DAUGHTERS.items():
        br = schema.parse_float(row, "br_%s_%s" % (name, pair))
        if schema.is_finite(br) and br > 0.0:
            particle.setDecayWidth(d1, d2, br * total_width)
    for target in schema.NEUTRALS:
        br = schema.parse_float(row, "br_%s_%sZ" % (name, target))
        if schema.is_finite(br) and br > 0.0:
            particle.setDecayWidth("Z", target, br * total_width)
    br = schema.parse_float(row, "br_%s_hcW" % name)
    if schema.is_finite(br) and br > 0.0:
        particle.setDecayWidth("W", "hc", br * total_width)


def _setup_charged(hc, row, HP):
    mass = schema.parse_float(row, schema.MASS_COLUMN["hc"])
    total_width = schema.parse_float(row, schema.TOTAL_WIDTH_COLUMN["hc"])
    hc.setMass(mass)
    if schema.is_finite(total_width) and total_width > 0.0:
        hc.setTotalWidth(total_width)
    for channel in schema.HC_DECAYS:
        br = schema.parse_float(row, "br_hc_%s" % channel)
        if schema.is_finite(br) and br > 0.0:
            hc.setBr(channel, br)
    for target in schema.NEUTRALS:
        br = schema.parse_float(row, "br_hc_%sW" % target)
        if schema.is_finite(br) and br > 0.0:
            hc.setBr("W", target, br)

    br_t_hcb = schema.parse_float(row, "br_t_hcb")
    kappa_t = schema.parse_float(row, "hc_kappa_t")
    kappa_b = schema.parse_float(row, "hc_kappa_b")
    if not schema.is_finite(br_t_hcb):
        br_t_hcb = 0.0
    if schema.is_finite(kappa_t) and schema.is_finite(kappa_b):
        cxn = HP.EffectiveCouplingCxns.ppHpmtb(
            "LHC13", mass, kappa_t, kappa_b, br_t_hcb
        )
        hc.setCxn("LHC13", "Hpmtb", cxn)
    if br_t_hcb > 0.0:
        hc.setCxn("LHC13", "brtHpb", br_t_hcb)
        hc.setCxn("LHC8", "brtHpb", br_t_hcb)


def width_rel_diff_max(pred, row):
    """Largest relative deviation between the HiggsTools total widths and
    the 2HDMC total widths, over all four Higgs bosons.

    effectiveCouplingInput reconstructs the SM-channel widths from the
    effective couplings, so the reconstructed total differs from 2HDMC's
    at the level of the effective-coupling approximation. Large values
    indicate an inconsistent input row.
    """
    worst = 0.0
    for name in ("h1", "h2", "h3", "hc"):
        reference = schema.parse_float(row, schema.TOTAL_WIDTH_COLUMN[name])
        if not (schema.is_finite(reference) and reference > 0.0):
            continue
        reconstructed = pred.particle(name).totalWidth()
        rel = abs(reconstructed - reference) / reference
        if rel > worst:
            worst = rel
    return worst


def build_predictions(row, HP):
    """Build a Predictions object for one theory_ok row.

    Returns (predictions, diagnostics) where diagnostics currently holds
    width_rel_diff_max.
    """
    if not schema.parse_flag(row, "hbhs_block_ok"):
        raise ValueError("row has no HBHS input block (hbhs_block_ok != 1)")

    pred = HP.Predictions()
    for name in schema.NEUTRALS:
        particle = pred.addParticle(
            HP.BsmParticle(name, "neutral", CP_ASSIGNMENT[name])
        )
        particle.setMass(schema.parse_float(row, schema.MASS_COLUMN[name]))
        coups = neutral_eff_couplings(row, name, HP)
        HP.effectiveCouplingInput(
            particle, coups, calcggH=False, calcHgamgam=False
        )
        _add_neutral_bsm_decays(particle, row, name)

    hc = pred.addParticle(HP.BsmParticle("hc", "single", "undefined"))
    _setup_charged(hc, row, HP)

    diagnostics = {"width_rel_diff_max": width_rel_diff_max(pred, row)}
    return pred, diagnostics
