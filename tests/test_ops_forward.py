import pytest

from dfxm_geo_mcp.ops.forward import PREVIEW_CAPS, run_forward  # noqa: F401


def test_analytic_preview_returns_png_without_a_kernel():
    res = run_forward("")  # empty -> default Al 111, forced analytic, no kernel
    assert res.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert res.stats["backend"] == "analytic"
    assert res.stats["kernel"] is None
    assert len(res.stats["shape"]) == 2


def test_over_cap_npixels_is_refused():
    toml = "[detector_geometry]\nNpixels = 512\n"
    with pytest.raises(ValueError, match="preview"):
        run_forward(toml)


def test_invalid_config_raises_before_compute():
    with pytest.raises(ValueError):
        run_forward("[scan.phi]\nvalue = 0.0\nrange = 0.001\n")  # range without steps


def test_mc_fidelity_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        run_forward("", fidelity="mc")
