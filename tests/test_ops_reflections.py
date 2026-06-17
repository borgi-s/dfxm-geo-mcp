import math

from dfxm_geo_mcp.ops.reflections import find_reflections


def test_default_al_mount_returns_records():
    recs = find_reflections("")  # empty -> default Al cubic mount @ 17 keV
    assert len(recs) > 0
    assert all(r.reachable for r in recs)
    assert all(math.isfinite(r.theta_deg) for r in recs)


def test_hcp_0002_flagged_unreachable_or_absent():
    # Ti hexagonal mount with the orthonormal mount required for hexagonal cells.
    # mount_x=[2,-1,0], mount_y=[0,1,0], mount_z=[0,0,1] — the mount used in all
    # HCP examples and tests (docs/crystal-structures.md, lines 142-154).
    # (0002) is NOT Laue-reachable at 17 keV for this mount (doc line ~183).
    toml = (
        "[crystal]\n"
        'lattice = "hexagonal"\n'
        "a = 2.951e-10\nc = 4.684e-10\n"
        'structure_type = "hcp"\n'
        'material = "Ti"\n'
        "mount_x = [2, -1, 0]\n"
        "mount_y = [0,  1, 0]\n"
        "mount_z = [0,  0, 1]\n"
    )
    recs = find_reflections(toml, hkl_max=2)
    # Enumeration must have run and returned at least one reflection.
    assert len(recs) > 0, "find_reflections returned empty list — mount/enumeration broken"
    # (0,0,2) must not appear as a reachable record (physics: not Laue-reachable at 17 keV).
    assert not any(r.hkl == (0, 0, 2) and r.reachable for r in recs)
