"""Tests for kernel cache discovery (Task 11).

Naming convention verified against dfxm_geo/reciprocal_space/kernel.py line 302:
  f"Resq_i_h{h}_k{k}_l{l}_{keV:g}keV_{date}.npz"
The :g format drops trailing zeros: 17.0 -> "17", 17.5 -> "17.5".
Fake kernel filenames in these tests use the REAL pattern, not the brief's "17.0keV" guess.
"""

from dfxm_geo_mcp import kernels


def test_kernel_absent_on_empty_cache():
    assert kernels.kernel_present((9, 9, 9), 17.0) is False


def test_present_after_a_fake_kernel_is_dropped_in(tmp_path, monkeypatch):
    from dfxm_geo_mcp import runtime

    fake_cache = tmp_path / "kernels"
    fake_cache.mkdir()
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    # Real convention: {keV:g} -> "17" not "17.0"
    (fake_cache / "Resq_i_h1_k1_l1_17keV_20260101.npz").write_bytes(b"x")
    assert kernels.kernel_present((1, 1, 1), 17.0) is True
    assert "Resq_i_h1_k1_l1_17keV_20260101" in "".join(kernels.cached_kernel_names())
