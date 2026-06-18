"""Integration tests: the MCP Apps wiring on run_forward and its UI resource."""

from __future__ import annotations

import pytest
from fastmcp import Client, Context

from dfxm_geo_mcp.server import mcp
from dfxm_geo_mcp.ui.forward_preview import FORWARD_PREVIEW_URI


@pytest.mark.asyncio
async def test_ui_resource_registered_with_mcp_app_mime():
    async with Client(mcp) as client:
        uris = {str(r.uri) for r in await client.list_resources()}
        assert FORWARD_PREVIEW_URI in uris
        blocks = await client.read_resource(FORWARD_PREVIEW_URI)
    assert any(getattr(b, "mimeType", "") == "text/html;profile=mcp-app" for b in blocks)


@pytest.mark.asyncio
async def test_run_forward_meta_links_both_clients():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    meta = tools["run_forward"].meta
    assert meta["ui"]["resourceUri"] == FORWARD_PREVIEW_URI
    assert meta["openai/outputTemplate"] == FORWARD_PREVIEW_URI


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_ui_branch_when_extension_supported(monkeypatch, tmp_path):
    # Force the UI-capable branch regardless of what the in-memory client advertises.
    monkeypatch.setattr(Context, "client_supports_extension", lambda self, ext: True)
    out = tmp_path / "p.png"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_forward", {"toml_text": "", "output_path": str(out)}
        )
    assert any(getattr(c, "type", None) == "image" for c in result.content)
    assert out.exists()  # file fallback always written
