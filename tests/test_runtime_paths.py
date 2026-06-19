"""resolve_output_path: enforce a suffix, and remap the Cowork POSIX-absolute
path ONLY when running on Windows (where a leading-/ path is drive-relative)."""

from __future__ import annotations

import os
from pathlib import Path

from dfxm_geo_mcp import runtime


def test_none_returns_default():
    default = Path("/tmp/d.html")
    assert runtime.resolve_output_path(None, default=default, suffix=".html") == default


def test_suffix_enforced_when_missing(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    out = runtime.resolve_output_path("/tmp/x.txt", default=Path("/tmp/d.html"), suffix=".html")
    assert out.name == "x.html"


def test_posix_absolute_on_windows_is_remapped(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    out = runtime.resolve_output_path(
        "/mnt/user-data/outputs/vis.html", default=tmp_path / "d.html", suffix=".html"
    )
    assert out.parent == tmp_path / "previews"
    assert out.name == "vis.html"


def test_windows_drive_path_passthrough(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    out = runtime.resolve_output_path("C:/proj/out.html", default=Path("d.html"), suffix=".html")
    assert "previews" not in str(out)
    assert out.name == "out.html"


def test_posix_leading_slash_not_remapped_on_posix(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    out = runtime.resolve_output_path(
        "/mnt/user-data/outputs/vis.html", default=tmp_path / "d.html", suffix=".html"
    )
    assert "previews" not in str(out)
    assert out.name == "vis.html"
