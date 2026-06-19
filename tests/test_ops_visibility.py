"""predict_visibility scoring core + slip-family resolution."""

from __future__ import annotations

import tomllib

import pytest

from dfxm_geo.crystal.slip_systems import slip_systems
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops import visibility as vis
from dfxm_geo_mcp.ops.types import VisibilityResult

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


def test_defect_mode_rows_sorted_descending_and_deterministic():
    res = vis.predict_visibility("", burgers=(1, -1, 0), hkl_max=2)
    assert isinstance(res, VisibilityResult)
    assert res.mode == "defect"
    assert res.structure == "fcc"
    assert res.matrix_rows == [] and res.systems == []
    assert len(res.defect_rows) > 0
    cosines = [r.gb_cos for r in res.defect_rows]
    assert cosines == sorted(cosines, reverse=True)
    # determinism
    res2 = vis.predict_visibility("", burgers=(1, -1, 0), hkl_max=2)
    assert [r.refl.hkl for r in res2.defect_rows] == [r.refl.hkl for r in res.defect_rows]
    # always-on edge caveat present
    assert any("g.(b x u)" in c for c in res.caveats)


def test_matrix_mode_shape_and_column_alignment():
    res = vis.predict_visibility("", hkl_max=2)  # FCC, no burgers -> matrix
    assert res.mode == "matrix"
    assert res.defect_rows == [] and res.burgers is None
    assert len(res.systems) == 12  # FCC {111}<110>
    assert len(res.matrix_rows) == len(vis.find_reflections("", hkl_max=2))
    for row in res.matrix_rows:
        assert len(row.cells) == len(res.systems)
    # alignment (not just shape): recompute one cell independently
    from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml
    mount = _crystal_mount_from_toml(None)
    row = res.matrix_rows[0]
    i = 0
    expected, _ = vis._score(mount, row.refl.hkl, res.systems[i].burgers, res.threshold_deg)
    assert row.cells[i] == pytest.approx(expected, abs=1e-12)


def test_matrix_mode_bcc_has_24_columns():
    toml = (
        "[reciprocal]\nhkl = [1, 1, 0]\nkeV = 17.0\nbackend = \"analytic\"\nbeamstop = false\n"
        "[crystal]\n"
        'lattice = "cubic"\na = 2.87e-10\n'
        'structure_type = "bcc"\n'
        'material = "Fe"\n'
        "mount_x = [1, 1, 0]\nmount_y = [-1, 1, 0]\nmount_z = [0, 0, 1]\n"
        "[geometry]\n"
        'mode = "oblique"\n'
        # eta is cross-checked by the validator, but predict_visibility never runs
        # the validator; find_reflections only needs the mount + energy.
    )
    res = vis.predict_visibility(toml, hkl_max=2)
    assert res.structure == "bcc"
    assert len(res.systems) == 24


def test_matrix_mode_hcp_has_reachable_basal_invisible_cell():
    res = vis.predict_visibility(HCP_TOML, hkl_max=2)
    assert res.structure == "hcp"
    basal_cols = [i for i, s in enumerate(res.systems) if s.family == "{0001}<11-20>"]
    assert basal_cols
    invisible_cut = float(__import__("numpy").cos(__import__("numpy").deg2rad(80.0)))
    found = any(
        row.cells[i] < invisible_cut for row in res.matrix_rows for i in basal_cols
    )
    assert found, "expected at least one reachable HCP basal-<a> cell to be invisible"


def test_matrix_mode_family_narrowing_with_alias():
    res = vis.predict_visibility(HCP_TOML, slip_families=["basal"], hkl_max=2)
    assert res.resolved_families == ["{0001}<11-20>"]
    assert all(s.family == "{0001}<11-20>" for s in res.systems)
    # narrowing echoes a caveat naming the canonical family
    assert any("{0001}<11-20>" in c for c in res.caveats)


def test_empty_reachable_returns_empty_rows_with_caveat(monkeypatch):
    monkeypatch.setattr(vis, "find_reflections", lambda toml_text, hkl_max=3: [])
    res = vis.predict_visibility("", burgers=(1, -1, 0))
    assert res.defect_rows == []
    assert any("reachable" in c.lower() for c in res.caveats)


def test_burgers_wrong_length_raises():
    with pytest.raises(ValueError):
        vis.predict_visibility("", burgers=(1, 0))  # only 2 ints


def test_arg_range_validation():
    with pytest.raises(ValueError):
        vis.predict_visibility("", hkl_max=0)
    with pytest.raises(ValueError):
        vis.predict_visibility("", threshold_deg=0.0)
    with pytest.raises(ValueError):
        vis.predict_visibility("", threshold_deg=90.0)
