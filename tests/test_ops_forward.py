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
