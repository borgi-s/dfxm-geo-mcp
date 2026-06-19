"""predict_visibility scoring core + slip-family resolution."""

from __future__ import annotations

import tomllib

import pytest

from dfxm_geo.crystal.slip_systems import slip_systems
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops import visibility as vis

HCP_TOML = (
    "[crystal]\n"
    'lattice = "hexagonal"\n'
    "a = 2.951e-10\nc = 4.684e-10\n"
    'structure_type = "hcp"\n'
    'material = "Ti"\n'
    "mount_x = [2, -1, 0]\n"
    "mount_y = [0,  1, 0]\n"
    "mount_z = [0,  0, 1]\n"
)


def _fcc_mount():
    return _crystal_mount_from_toml(None)


def _hcp_mount():
    return _crystal_mount_from_toml(tomllib.loads(HCP_TOML)["crystal"])


def test_fcc_screw_invisibility_golden():
    # Textbook g.b = 0: g=(1,1,1) perpendicular to b=[1,-1,0].
    gbcos, band = vis._score(_fcc_mount(), (1, 1, 1), (1, -1, 0), 10.0)
    assert gbcos == pytest.approx(0.0, abs=1e-9)
    assert band == "invisible"


def test_fcc_strong_control_golden():
    gbcos, band = vis._score(_fcc_mount(), (2, 0, 0), (1, -1, 0), 10.0)
    assert gbcos == pytest.approx(0.70710678, abs=1e-6)
    assert band == "strong"


def test_hcp_basal_a_invisible_against_0002_golden():
    # Scoring-core level on purpose: (0002) is NOT Laue-reachable at 17 keV for
    # the HCP mount, so it never appears in matrix_rows/defect_rows. Mirrors the
    # library's test_screw_gb_extinction.
    mount = _hcp_mount()
    for s in slip_systems("hcp", families=["{0001}<11-20>"]):
        gbcos, band = vis._score(mount, (0, 0, 2), s.b, 10.0)
        assert gbcos == pytest.approx(0.0, abs=1e-9)
        assert band == "invisible"


def test_band_matches_gb_visible_threshold():
    # The 10-degree boundary: cos(90-10) = cos(80) ~ 0.17365.
    assert vis._band(0.18, 10.0) == "weak"
    assert vis._band(0.17, 10.0) == "invisible"
    assert vis._band(0.6, 10.0) == "strong"
    assert vis._band(0.5, 10.0) == "strong"   # STRONG_CUT is inclusive
    assert vis._band(0.49, 10.0) == "weak"


def test_resolve_families_alias_and_passthrough():
    # friendly alias resolves to canonical
    assert vis._resolve_families("hcp", ["basal"]) == ["{0001}<11-20>"]
    # a literal registry string passes through unchanged
    assert vis._resolve_families("hcp", ["{10-10}<11-20>"]) == ["{10-10}<11-20>"]
    # None -> None (no narrowing)
    assert vis._resolve_families("fcc", None) is None
    # FCC takes its registry string directly
    assert vis._resolve_families("fcc", ["{111}<110>"]) == ["{111}<110>"]


def test_resolve_families_unknown_raises_listing_both():
    with pytest.raises(ValueError) as exc:
        vis._resolve_families("hcp", ["bogus"])
    msg = str(exc.value)
    assert "basal" in msg                # accepted aliases listed
    assert "{0001}<11-20>" in msg        # registry families listed


def test_resolve_families_alias_for_wrong_structure_raises():
    # "basal" is an HCP-only alias; on FCC it must raise (canonical not in registry)
    with pytest.raises(ValueError):
        vis._resolve_families("fcc", ["basal"])


def test_alias_map_validates_against_live_registry():
    # Every alias canonical must be a real hcp family (guard against registry drift).
    hcp_families = {s.family for s in slip_systems("hcp")}
    for canonical in vis._HCP_ALIASES.values():
        assert canonical in hcp_families
