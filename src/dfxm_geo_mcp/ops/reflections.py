"""find_reflections: enumerate Laue-reachable reflections for a config's mount + energy."""

from __future__ import annotations

import math
import tomllib

from dfxm_geo.crystal.oblique import find_reflections as _find
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops.types import ReflectionRecord


def find_reflections(toml_text: str, *, hkl_max: int = 3) -> list[ReflectionRecord]:
    """Enumerate Laue-reachable reflections up to hkl_max; angles returned in degrees."""
    data = tomllib.loads(toml_text) if toml_text.strip() else {}
    mount = _crystal_mount_from_toml(data.get("crystal"))
    keV = float(data.get("reciprocal", {}).get("keV", 17.0))

    records: list[ReflectionRecord] = []
    for geom in _find(mount, keV, hkl_max=hkl_max):
        if not math.isnan(geom.theta_1):
            theta, eta, omega = geom.theta_1, geom.eta_1, geom.omega_1
        else:
            theta, eta, omega = geom.theta_2, geom.eta_2, geom.omega_2
        records.append(
            ReflectionRecord(
                hkl=geom.hkl,
                theta_deg=math.degrees(theta),
                eta_deg=math.degrees(eta),
                omega_deg=math.degrees(omega),
                energy_keV=keV,
                reachable=True,
                note="",
            )
        )
    return records
