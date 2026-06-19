"""predict_visibility: score dislocation visibility (g.b) across reachable reflections.

Thin glue over dfxm-geo — no new physics. The scoring core composes the
library's ``gb_cos`` with the A/B frame convention; the assembly (Task 5) reuses
``ops.reflections.find_reflections`` for the reachable set and
``crystal.slip_systems.slip_systems`` for the matrix columns.
"""

from __future__ import annotations

import tomllib

import numpy as np

from dfxm_geo.crystal.burgers import gb_cos
from dfxm_geo.crystal.slip_systems import slip_systems
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops.reflections import find_reflections
from dfxm_geo_mcp.ops.types import (
    DefectRow,
    MatrixRow,
    ReflGeom,
    SlipSystemLabel,
    VisibilityResult,
)

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


def predict_visibility(
    toml_text: str,
    *,
    burgers: tuple[int, ...] | None = None,
    slip_families: list[str] | None = None,
    hkl_max: int = 3,
    threshold_deg: float = 10.0,
) -> VisibilityResult:
    """Score dislocation visibility (g.b) across the config's reachable reflections.

    Two modes: defect-first (``burgers`` given) ranks reflections by gb_cos for
    that one Burgers vector; survey/matrix (``burgers`` omitted) scores every
    reachable reflection against every slip system of the resolved structure.
    """
    if not 1 <= hkl_max <= 6:
        raise ValueError(f"hkl_max must be between 1 and 6 (got {hkl_max})")
    if not 0.0 < threshold_deg < 90.0:
        raise ValueError(f"threshold_deg must be in (0, 90) (got {threshold_deg})")

    data = tomllib.loads(toml_text) if toml_text.strip() else {}
    try:
        mount = _crystal_mount_from_toml(data.get("crystal"))
    except Exception as exc:  # unparseable / unbuildable mount
        raise ValueError(f"could not build a crystal mount from the config: {exc}") from exc
    keV = float(data.get("reciprocal", {}).get("keV", 17.0))
    structure = mount.resolved_structure_type

    refls = find_reflections(toml_text, hkl_max=hkl_max)
    caveats = [EDGE_CAVEAT]
    if not refls:
        caveats.append(
            "No Laue-reachable reflections at this energy/mount up to "
            f"hkl_max={hkl_max}; nothing to score."
        )

    def _geom(r: object) -> ReflGeom:
        return ReflGeom(
            hkl=r.hkl, theta_deg=r.theta_deg, eta_deg=r.eta_deg, omega_deg=r.omega_deg  # type: ignore[attr-defined]
        )

    if burgers is not None:
        b = tuple(int(x) for x in burgers)
        if len(b) != 3:
            raise ValueError(f"burgers must have exactly 3 Miller indices, got {len(b)}: {b}")
        defect_rows: list[DefectRow] = []
        for r in refls:
            value, band = _score(mount, r.hkl, b, threshold_deg)
            defect_rows.append(DefectRow(refl=_geom(r), gb_cos=value, visibility=band))
        defect_rows.sort(key=lambda d: d.gb_cos, reverse=True)
        return VisibilityResult(
            mode="defect",
            structure=structure,
            energy_keV=keV,
            burgers=b,
            threshold_deg=threshold_deg,
            resolved_families=[],
            systems=[],
            defect_rows=defect_rows,
            matrix_rows=[],
            caveats=caveats,
        )

    resolved = _resolve_families(structure, slip_families)
    try:
        systems = slip_systems(structure, families=resolved)
    except ValueError as exc:
        raise ValueError(
            f"structure {structure!r} has no registered slip systems; register one "
            f"with dfxm_geo.crystal.slip_systems.register_custom. ({exc})"
        ) from exc
    if not systems:
        raise ValueError(f"no slip systems for structure {structure!r} with families={resolved!r}")

    labels = [SlipSystemLabel(plane=s.n, burgers=s.b, family=s.family) for s in systems]
    matrix_rows: list[MatrixRow] = []
    for r in refls:
        cells = [_score(mount, r.hkl, s.b, threshold_deg)[0] for s in systems]
        matrix_rows.append(MatrixRow(refl=_geom(r), cells=cells))

    resolved_families = (
        resolved if resolved is not None else list(dict.fromkeys(s.family for s in systems))
    )
    if resolved is not None:
        caveats.append("Slip families narrowed to: " + ", ".join(resolved) + ".")

    return VisibilityResult(
        mode="matrix",
        structure=structure,
        energy_keV=keV,
        burgers=None,
        threshold_deg=threshold_deg,
        resolved_families=resolved_families,
        systems=labels,
        defect_rows=[],
        matrix_rows=matrix_rows,
        caveats=caveats,
    )
