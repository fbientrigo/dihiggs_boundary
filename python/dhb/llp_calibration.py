"""Versioned Trackless response calibration for the LLP signal layer.

Production normalization is intentionally *not* part of this calibration.
Each physical model point must carry its own MadGraph cross section into
``dhb.llp_signal``.  This module owns only the external recast response,
normalization constants and interpolation inside the declared support.
"""

import math


CALIBRATION_SCHEMA_VERSION = "dhb.llp_signal_calibration.v2"
ALLOWED_STATUSES = {"PROVISIONAL", "VALIDATED"}


class CalibrationError(ValueError):
    pass


def _finite(value, name):
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise CalibrationError("%s must be numeric" % name)
    if not math.isfinite(out):
        raise CalibrationError("%s must be finite" % name)
    return out


def validate_calibration(data):
    """Validate and normalize a Trackless-response calibration dict."""
    if not isinstance(data, dict):
        raise CalibrationError("calibration must be a mapping")
    if data.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise CalibrationError("unsupported calibration schema_version")

    version = str(data.get("calibration_version", "")).strip()
    status = str(data.get("calibration_status", "")).strip().upper()
    if not version:
        raise CalibrationError("calibration_version is required")
    if status not in ALLOWED_STATUSES:
        raise CalibrationError("calibration_status must be PROVISIONAL or VALIDATED")

    try:
        domain = data["domain"]
        mass = domain["m_H2_GeV"]
        acceptance = data["acceptance"]
        normalization = data["normalization"]
        classification = data["classification"]
    except KeyError as exc:
        raise CalibrationError("missing calibration section/key: %s" % exc)

    mass_value = _finite(mass.get("value"), "domain.m_H2_GeV.value")
    mass_tol = _finite(mass.get("abs_tolerance"), "domain.m_H2_GeV.abs_tolerance")
    ctau_min = _finite(domain.get("ctau_min_mm"), "domain.ctau_min_mm")
    ctau_max = _finite(domain.get("ctau_max_mm"), "domain.ctau_max_mm")
    if mass_value <= 0.0 or mass_tol < 0.0 or ctau_min <= 0.0 or ctau_max <= ctau_min:
        raise CalibrationError("invalid calibration domain")

    if acceptance.get("analysis") != "Trackless":
        raise CalibrationError("acceptance.analysis must be Trackless")
    if acceptance.get("model") != "log_linear_ctau":
        raise CalibrationError("acceptance.model must be log_linear_ctau")
    points = acceptance.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise CalibrationError("acceptance.points must contain at least two rows")
    normalized_points = []
    previous_ctau = None
    for index, point in enumerate(points):
        ctau = _finite(point.get("ctau_mm"), "acceptance.points[%d].ctau_mm" % index)
        aeff = _finite(point.get("aeff"), "acceptance.points[%d].aeff" % index)
        unc = _finite(point.get("aeff_unc", 0.0), "acceptance.points[%d].aeff_unc" % index)
        if ctau <= 0.0 or not (0.0 <= aeff <= 1.0) or unc < 0.0:
            raise CalibrationError("invalid acceptance point at index %d" % index)
        if previous_ctau is not None and ctau <= previous_ctau:
            raise CalibrationError("acceptance.points must be strictly increasing in ctau_mm")
        previous_ctau = ctau
        normalized_points.append((ctau, aeff, unc))
    if normalized_points[0][0] > ctau_min or normalized_points[-1][0] < ctau_max:
        raise CalibrationError("acceptance table does not cover declared ctau domain")

    luminosity = _finite(normalization.get("luminosity_fb"), "normalization.luminosity_fb")
    s95 = _finite(normalization.get("S95"), "normalization.S95")
    near_fraction = _finite(classification.get("near_fraction"), "classification.near_fraction")
    if luminosity <= 0.0 or s95 <= 0.0 or not (0.0 <= near_fraction < 1.0):
        raise CalibrationError("invalid normalization/classification settings")

    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "calibration_version": version,
        "calibration_status": status,
        "domain": {
            "mass_value": mass_value,
            "mass_tolerance": mass_tol,
            "ctau_min": ctau_min,
            "ctau_max": ctau_max,
        },
        "acceptance_points": normalized_points,
        "luminosity_fb": luminosity,
        "S95": s95,
        "near_fraction": near_fraction,
        "provenance": data.get("provenance", {}),
    }


def mass_supported(calibration, m_H2_GeV):
    domain = calibration["domain"]
    return abs(m_H2_GeV - domain["mass_value"]) <= domain["mass_tolerance"]


def ctau_supported(calibration, ctau_mm):
    domain = calibration["domain"]
    return domain["ctau_min"] <= ctau_mm <= domain["ctau_max"]


def acceptance_response(calibration, ctau_mm):
    """Interpolate Aeff and its absolute uncertainty linearly in log(ctau).

    No extrapolation is performed. Call ``ctau_supported`` first.
    """
    points = calibration["acceptance_points"]
    for ctau, aeff, unc in points:
        if math.isclose(ctau_mm, ctau, rel_tol=0.0, abs_tol=max(1e-15, 1e-12 * ctau)):
            return aeff, unc
    logx = math.log(ctau_mm)
    for left, right in zip(points[:-1], points[1:]):
        if left[0] <= ctau_mm <= right[0]:
            logl = math.log(left[0])
            logr = math.log(right[0])
            weight = (logx - logl) / (logr - logl)
            aeff = left[1] + weight * (right[1] - left[1])
            unc = left[2] + weight * (right[2] - left[2])
            return aeff, unc
    raise CalibrationError("ctau outside interpolation support")


def threshold_class(calibration, ratio):
    band = calibration["near_fraction"]
    if ratio < 1.0 - band:
        return "BELOW"
    if ratio <= 1.0 + band:
        return "NEAR"
    return "ABOVE"
