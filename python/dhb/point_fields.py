"""Resolve LLP observables across legacy boundary and canonical dihiggs rows.

This module is a migration bridge, not a physics producer. It never reconstructs
2HDM points or recomputes the h-H2-H2 coupling. It only resolves equivalent
serialized names and derives BR(H2->bb) from same-row widths when the direct BR
is absent.
"""

import math


ALIASES = {
    "m_H2_GeV": ("m_H2_GeV", "mH_input_GeV", "mH", "m_phi"),
    "g_hH2H2_GeV": ("g_hH2H2_GeV",),
    "ctau_mm_H2": ("ctau_mm_H2", "ctau_mm"),
    "br_bb_H2": ("br_bb_H2", "br_bb"),
    "total_width_H2": ("total_width_H2", "total_width_GeV"),
    "width_bb_H2": ("width_bb_H2", "width_bb_GeV"),
}


def _float(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return float("nan")
    return value if math.isfinite(value) else float("nan")


def _close(a, b, rel_tol=1e-9, abs_tol=1e-15):
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def resolve_alias(row, canonical_name):
    """Return ``(value, source, issue)`` for one canonical observable.

    All finite aliases present in the same row must agree. Conflicting aliases
    fail closed instead of silently picking one serialized name over another.
    """
    found = []
    for name in ALIASES[canonical_name]:
        if name not in row or str(row.get(name, "")).strip() == "":
            continue
        value = _float(row.get(name))
        if not math.isfinite(value):
            # A populated alias is evidence about this observable.  Treating a
            # malformed canonical value as if it were absent would let a legacy
            # alias (or the BR width bridge) silently replace corrupted input.
            return float("nan"), "", "invalid:%s" % canonical_name
        found.append((name, value))
    if not found:
        return float("nan"), "", "missing:%s" % canonical_name
    reference = found[0][1]
    for name, value in found[1:]:
        if not _close(reference, value):
            return (
                float("nan"),
                "",
                "conflicting_aliases:%s:%s" % (canonical_name, ",".join(n for n, _ in found)),
            )
    return reference, found[0][0], ""


def resolve_signal_inputs(row):
    """Resolve the physical inputs needed by ``dhb.llp_signal``.

    BR(bb) has one owner here during the migration: prefer an explicit BR, else
    derive it exactly once from same-row ``width_bb / total_width``. If both are
    available they must agree within tolerance.
    """
    result = {}
    sources = {}
    issues = []

    for name in ("m_H2_GeV", "g_hH2H2_GeV", "ctau_mm_H2"):
        value, source, issue = resolve_alias(row, name)
        result[name] = value
        sources[name] = source
        if issue:
            issues.append(issue)

    direct_br, br_source, br_issue = resolve_alias(row, "br_bb_H2")
    total_width, total_source, total_issue = resolve_alias(row, "total_width_H2")
    width_bb, width_source, width_issue = resolve_alias(row, "width_bb_H2")

    derived_br = float("nan")
    if math.isfinite(total_width) and total_width > 0.0 and math.isfinite(width_bb):
        derived_br = width_bb / total_width

    if br_issue.startswith("invalid:"):
        # An explicit BR is authoritative when supplied.  Do not turn a
        # malformed explicit value into a numerical signal via width fallback.
        result["br_bb_H2"] = float("nan")
        sources["br_bb_H2"] = ""
        issues.append(br_issue)
    elif math.isfinite(direct_br):
        result["br_bb_H2"] = direct_br
        sources["br_bb_H2"] = br_source
        if math.isfinite(derived_br) and not _close(direct_br, derived_br, rel_tol=1e-6):
            issues.append("conflicting_br_bb_and_width_ratio")
            result["br_bb_H2"] = float("nan")
            sources["br_bb_H2"] = ""
    elif math.isfinite(derived_br):
        result["br_bb_H2"] = derived_br
        sources["br_bb_H2"] = "%s/%s" % (width_source, total_source)
        # direct_br being absent is expected when derivation succeeds.
    else:
        result["br_bb_H2"] = float("nan")
        sources["br_bb_H2"] = ""
        issues.append(br_issue or "missing:br_bb_H2")
        if total_issue:
            issues.append(total_issue)
        if width_issue:
            issues.append(width_issue)

    # Physical-domain validation is deliberately narrow. These checks do not
    # decide theory or experimental validity; they only protect signal arithmetic.
    if math.isfinite(result["m_H2_GeV"]) and result["m_H2_GeV"] <= 0.0:
        issues.append("invalid:m_H2_GeV")
        result["m_H2_GeV"] = float("nan")
    if math.isfinite(result["g_hH2H2_GeV"]) and result["g_hH2H2_GeV"] < 0.0:
        issues.append("invalid:g_hH2H2_GeV_must_be_nonnegative_magnitude")
        result["g_hH2H2_GeV"] = float("nan")
    if math.isfinite(result["ctau_mm_H2"]) and result["ctau_mm_H2"] <= 0.0:
        issues.append("invalid:ctau_mm_H2")
        result["ctau_mm_H2"] = float("nan")
    if math.isfinite(result["br_bb_H2"]) and not (0.0 <= result["br_bb_H2"] <= 1.0):
        issues.append("invalid:br_bb_H2")
        result["br_bb_H2"] = float("nan")

    return result, sources, sorted(set(i for i in issues if i))
