import pytest

from dfxm_geo_mcp.ops.rocking import ROCKING_CAPS, run_rocking  # noqa: F401

_TINY = {"max_npixels": 32, "max_nsub": 1, "max_frames": 41}


@pytest.mark.slow
def test_run_rocking_keeps_every_frame_and_traces_a_curve():
    res = run_rocking("", n_frames=5, phi_max=6e-4, caps=_TINY)
    assert len(res.frames_png) == 5
    assert len(res.phis) == 5
    assert len(res.intensities) == 5
    # Centered scan: index 0 is one end (a weak tail), last is the other.
    assert res.phis[0] == pytest.approx(-6e-4)
    assert res.phis[-1] == pytest.approx(6e-4)
    # Every frame is a real PNG rendered on the shared color scale.
    assert all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in res.frames_png)
    assert res.vmax > res.vmin
    # The rocking curve is not flat (phi actually changed the physics).
    assert max(res.intensities) > min(res.intensities)
    assert res.meta["n_frames"] == 5


def test_run_rocking_rejects_over_cap_frames():
    with pytest.raises(ValueError, match="frames"):
        run_rocking("", n_frames=999)


def test_run_rocking_rejects_bad_phi_max():
    with pytest.raises(ValueError):
        run_rocking("", phi_max=0.0)


def test_run_rocking_rejects_over_cap_nsub():
    # Mirror run_forward's contract: an explicit over-cap Nsub is a clear error,
    # not a silent downgrade.
    with pytest.raises(ValueError, match="Nsub"):
        run_rocking("[detector_geometry]\nNsub = 64\n")
