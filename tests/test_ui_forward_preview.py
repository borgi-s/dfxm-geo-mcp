"""Unit tests for the forward-preview presentation module (no MCP transport)."""

from __future__ import annotations

from fastmcp.tools.tool import ToolResult

from dfxm_geo_mcp.ui.forward_preview import (
    FORWARD_PREVIEW_HTML,
    FORWARD_PREVIEW_URI,
    build_forward_result,
)

_STATS = {
    "shape": (128, 128),
    "vmin": 0.0,
    "vmax": 1.0,
    "backend": "analytic",
    "kernel": None,
    "wall_s": 0.1,
}
_PNG = b"\x89PNG\r\n\x1a\n" + b"fakepngbody"


def test_uri_is_ui_scheme():
    assert FORWARD_PREVIEW_URI == "ui://dfxm-geo/forward-preview.html"


def test_template_has_no_external_origins():
    # No absolute http(s) URLs => default CSP is sufficient (Global Constraints).
    assert "http://" not in FORWARD_PREVIEW_HTML
    assert "https://" not in FORWARD_PREVIEW_HTML


def test_unsupported_branch_returns_legacy_list():
    out = build_forward_result(_PNG, _STATS, "/tmp/p.png", supports_ui=False)
    assert isinstance(out, list)
    assert len(out) == 2
    assert isinstance(out[1], str)
    assert "/tmp/p.png" in out[1]


def test_supported_branch_carries_image_in_content_and_meta():
    out = build_forward_result(_PNG, _STATS, "/tmp/p.png", supports_ui=True)
    assert isinstance(out, ToolResult)
    img = next(c for c in out.content if c.type == "image")
    assert img.mimeType == "image/png"
    assert img.data  # base64 string, non-empty
    assert out.meta["image"]["mimeType"] == "image/png"
    assert out.meta["image"]["data"] == img.data
    # structured_content stays small and base64-free (model-visible)
    assert out.structured_content["backend"] == "analytic"
    assert out.structured_content["shape"] == [128, 128]
    assert "image" not in out.structured_content


def test_supported_branch_reports_saved_path():
    out = build_forward_result(_PNG, _STATS, "/tmp/p.png", supports_ui=True)
    texts = [c.text for c in out.content if c.type == "text"]
    assert any("/tmp/p.png" in t for t in texts)
