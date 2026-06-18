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


def test_mc_without_kernel_returns_needs_bootstrap():
    res = run_forward("", fidelity="mc")  # default Al -> (-1,1,-1)@17, no kernel cached
    assert res.needs_bootstrap is True
    assert res.bootstrap_hint is not None
    assert res.bootstrap_hint["hkl"] == [-1, 1, -1]
    assert res.bootstrap_hint["tool"] == "start_bootstrap"
    assert res.stats["backend"] == "mc"
    assert res.stats["kernel"] is None


def test_unknown_fidelity_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        run_forward("", fidelity="bogus")


def test_run_forward_writes_nothing_to_stdout(capsys):
    # stdio-discipline regression: the dfxm-geo forward sim prints a run summary to
    # stdout, which would corrupt the JSON-RPC stream when run over the stdio MCP
    # transport. run_forward must keep stdout pristine (library output -> stderr).
    run_forward("")
    captured = capsys.readouterr()
    assert captured.out == "", f"run_forward leaked to stdout: {captured.out!r}"


def test_render_png_returns_valid_annotated_png():
    import numpy as np

    from dfxm_geo_mcp.ops.forward import _render_png

    img = np.random.default_rng(0).random((32, 32))
    png = _render_png(img)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # A colorbar + axes make the figure non-trivial; guard against an empty render.
    assert len(png) > 2000


def test_render_png_honours_shared_vmin_vmax():
    import numpy as np

    from dfxm_geo_mcp.ops.forward import _render_png

    img = np.zeros((16, 16))
    img[0, 0] = 1.0
    a = _render_png(img, vmin=0.0, vmax=1.0)
    b = _render_png(img, vmin=0.0, vmax=1000.0)
    assert a[:8] == b"\x89PNG\r\n\x1a\n"
    # A different color scale must change the rendered bytes.
    assert a != b


def test_run_forward_populates_meta():
    res = run_forward("")
    assert res.meta is not None
    assert tuple(res.meta["reflection"]) == (-1, 1, -1)
    assert res.meta["energy_keV"] == 17.0
    assert res.meta["two_theta_deg"] > 0
