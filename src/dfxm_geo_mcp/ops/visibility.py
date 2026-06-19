"""predict_visibility: score dislocation visibility (g.b) across reachable reflections.

Thin glue over dfxm-geo — no new physics. The scoring core composes the
library's ``gb_cos`` with the A/B frame convention; the assembly (Task 5) reuses
``ops.reflections.find_reflections`` for the reachable set and
``crystal.slip_systems.slip_systems`` for the matrix columns.
"""

from __future__ import annotations

import numpy as np

from dfxm_geo.crystal.burgers import gb_cos
from dfxm_geo.crystal.slip_systems import slip_systems

# Strong vs weak split on gb_cos (presentational, NOT a contrast prediction).
STRONG_CUT = 0.5

# Always-on caveat: g.b alone under-predicts edge-dislocation visibility.
EDGE_CAVEAT = (
    "g.b = 0 is exact kinematic invisibility for screw character; edge "
    "dislocations can retain residual contrast via the g.(b x u) term not "
    "modelled here."
)

# Friendly -> canonical registry family names for HCP (the library's families=
# accepts only the literal registry strings). FCC/BCC have no common short names,
# so callers pass the registry strings directly. Validated against the live
# registry at import (see _validate_aliases below).
_HCP_ALIASES: dict[str, str] = {
    "basal": "{0001}<11-20>",
    "prismatic": "{10-10}<11-20>",
    "pyramidal-a": "{10-11}<11-20>",
    "pyramidal-ca-1": "{10-11}<11-23>",
    "pyramidal-ca-2": "{11-22}<11-23>",
}


def _validate_aliases() -> None:
    """Fail loudly at import if an alias canonical is no longer a real hcp family."""
    families = {s.family for s in slip_systems("hcp")}
    for friendly, canonical in _HCP_ALIASES.items():
        if canonical not in families:
            raise AssertionError(
                f"slip-family alias {friendly!r} -> {canonical!r} is not in the "
                f"live hcp registry {sorted(families)}"
            )


_validate_aliases()


def _band(gb_cos_value: float, threshold_deg: float) -> str:
    """Classify a gb_cos value into 'invisible' | 'weak' | 'strong'.

    Mirrors the library's ``gb_visible``: invisible when gb_cos is below
    cos(90 - threshold_deg); otherwise strong at/above STRONG_CUT, else weak.
    """
    visible_cut = float(np.cos(np.deg2rad(90.0 - threshold_deg)))
    if gb_cos_value < visible_cut:
        return "invisible"
    return "strong" if gb_cos_value >= STRONG_CUT else "weak"


def _score(
    mount: object,
    hkl: tuple[int, int, int],
    b_miller: tuple[int, ...],
    threshold_deg: float,
) -> tuple[float, str]:
    """Score one reflection against one Burgers vector. Returns (gb_cos, band).

    Frame convention (load-bearing): g = cell.B @ hkl (reciprocal), b = cell.A @
    b_miller (real-space). gb_cos normalizes both internally, so an un-normalized
    g and any non-zero b are fine.
    """
    g = mount.cell.B @ np.asarray(hkl, dtype=float)            # type: ignore[attr-defined]
    b = mount.cell.A @ np.asarray(b_miller, dtype=float)       # type: ignore[attr-defined]
    value = gb_cos(g, b)
    return value, _band(value, threshold_deg)


def _resolve_families(structure: str, slip_families: list[str] | None) -> list[str] | None:
    """Map each requested family to a canonical registry string for ``structure``.

    Resolution per entry: exact registry name -> pass through; known friendly
    alias whose canonical is in this structure's registry -> canonical; otherwise
    raise a ValueError listing BOTH the accepted aliases and the structure's
    registry families. ``None`` (no narrowing) returns ``None``.
    """
    if slip_families is None:
        return None
    registry = {s.family for s in slip_systems(structure)}
    resolved: list[str] = []
    for fam in slip_families:
        if fam in registry:
            resolved.append(fam)
        elif fam in _HCP_ALIASES and _HCP_ALIASES[fam] in registry:
            resolved.append(_HCP_ALIASES[fam])
        else:
            raise ValueError(
                f"unknown slip family {fam!r} for structure {structure!r}. "
                f"Accepted aliases: {sorted(_HCP_ALIASES)}. "
                f"Registry families: {sorted(registry)}."
            )
    return resolved
