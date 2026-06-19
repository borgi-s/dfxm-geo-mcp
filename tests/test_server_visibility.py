"""The predict_visibility MCP tool: structured dict + self-contained HTML."""

from __future__ import annotations

import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp


@pytest.mark.asyncio
async def test_predict_visibility_tool_is_registered():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert "predict_visibility" in names


@pytest.mark.asyncio
async def test_predict_visibility_defect_mode_writes_html_and_returns_sorted_rows(tmp_path):
    out = tmp_path / "vis.html"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "predict_visibility",
            {"toml_text": "", "burgers": [1, -1, 0], "hkl_max": 2, "output_path": str(out)},
        )
    data = result.data
    assert data["mode"] == "defect"
    assert data["html_path"] == str(out.resolve())
    cosines = [r["gb_cos"] for r in data["defect_rows"]]
    assert cosines == sorted(cosines, reverse=True)
    # HTML artifact written and self-contained
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "http://" not in text and "https://" not in text


@pytest.mark.asyncio
async def test_predict_visibility_matrix_mode_default_path(tmp_path, monkeypatch):
    from dfxm_geo_mcp import runtime

    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    async with Client(mcp) as client:
        result = await client.call_tool("predict_visibility", {"toml_text": "", "hkl_max": 2})
    data = result.data
    assert data["mode"] == "matrix"
    assert len(data["systems"]) == 12
    saved = tmp_path / "previews" / "visibility.html"
    assert saved.exists()
    assert data["html_path"] == str(saved.resolve())


@pytest.mark.asyncio
async def test_predict_visibility_rejects_bad_args():
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.call_tool("predict_visibility", {"toml_text": "", "hkl_max": 0})
        with pytest.raises(Exception):
            await client.call_tool("predict_visibility", {"toml_text": "", "threshold_deg": 95.0})
