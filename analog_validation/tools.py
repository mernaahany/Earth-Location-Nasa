"""Deterministic interval constraint checking, not a traversability simulator."""

from math import pi

from .models import Constraint, Feature, RecalculationResult

# unit -> dimension, scale and offset to canonical unit
UNITS = {
    "deg": ("angle", pi / 180, 0), "rad": ("angle", 1, 0),
    "K": ("temperature", 1, 0), "degC": ("temperature", 1, 273.15),
    "Pa": ("pressure", 1, 0), "kPa": ("pressure", 1000, 0),
    "m": ("length", 1, 0), "km": ("length", 1000, 0),
    "Wh": ("energy", 1, 0), "kWh": ("energy", 1000, 0),
    "h": ("time", 1, 0), "s": ("time", 1 / 3600, 0),
    "W": ("power", 1, 0), "1": ("ratio", 1, 0),
}


def check_constraint(feature: Feature | None, constraint: Constraint) -> RecalculationResult:
    assumptions = ("Direct mission-limit comparison; no slip or survival probability inferred.",
                   "Uncertainty is a bounded absolute interval; limit is configuration-defined.")
    missing = []
    if feature is None or feature.value is None:
        missing.append(constraint.feature)
    elif not feature.source or not feature.unit or feature.uncertainty is None or not feature.period:
        missing.extend(f"{constraint.feature}.{name}" for name, val in
                       (("source", feature.source), ("unit", feature.unit),
                        ("uncertainty", feature.uncertainty), ("period", feature.period)) if val is None or val == "")
    if missing:
        return RecalculationResult("constraint_interval_v1", "insufficient_evidence", "unknown",
                                   None, constraint.unit, None, assumptions, tuple(missing))
    left, right = UNITS.get(feature.unit), UNITS.get(constraint.unit)
    if left is None or right is None or left[0] != right[0]:
        return RecalculationResult("constraint_interval_v1", "requires_review", "unknown", None,
                                   constraint.unit, None, assumptions, ("compatible documented units",))
    value = (feature.value * left[1] + left[2] - right[2]) / right[1]
    uncertainty = feature.uncertainty * left[1] / right[1]
    if left[0] == "temperature" and value * right[1] + right[2] - uncertainty * right[1] < 0:
        return RecalculationResult("constraint_interval_v1", "requires_review", "unknown", None,
                                   constraint.unit, None, assumptions, ("physically valid temperature",))
    margin = constraint.limit - value if constraint.direction == "max" else value - constraint.limit
    bounds = (margin - uncertainty, margin + uncertainty)
    outcome = "pass" if bounds[0] >= 0 else "fail" if bounds[1] < 0 else "unknown"
    status = "model_predicted" if outcome != "unknown" else "requires_review"
    return RecalculationResult("constraint_interval_v1", status, outcome, value,
                               constraint.unit, bounds, assumptions)


# Explicit registry. Higher-fidelity models must be separately validated before registration.
TOOLS = {"constraint_interval_v1": check_constraint}
