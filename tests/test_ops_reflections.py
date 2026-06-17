import math

from dfxm_geo_mcp.ops.reflections import find_reflections


def test_default_al_mount_returns_records():
    recs = find_reflections("")  # empty -> default Al cubic mount @ 17 keV
    assert len(recs) > 0
    assert all(r.reachable for r in recs)
    assert all(math.isfinite(r.theta_deg) for r in recs)


def test_hcp_0002_flagged_unreachable_or_absent():
    # Ti hexagonal mount: (0002) is not Laue-reachable in the standard mount.
    toml = (
        "[crystal]\n"
        'lattice = "hexagonal"\n'
        "a = 2.95\nc = 4.68\n"
        'material = "Ti"\npoisson_ratio = 0.32\n'
    )
    recs = find_reflections(toml, hkl_max=2)
    # (0,0,2) must not appear as a reachable record.
    assert not any(r.hkl == (0, 0, 2) and r.reachable for r in recs)
