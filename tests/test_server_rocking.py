"""The run_rocking MCP tool writes a self-contained interactive HTML viewer."""

from __future__ import annotations

import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp


@pytest.mark.asyncio
async def test_run_rocking_tool_is_registered():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert "run_rocking" in names


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_rocking_tool_writes_interactive_html(tmp_path):
    out = tmp_path / "rock.html"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_rocking",
            {"toml_text": "", "n_frames": 5, "phi_max": 6e-4, "output_path": str(out)},
        )

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    # one embedded frame per phi
    assert text.count("data:image/png;base64,") >= 5
    assert 'type="range"' in text  # the scrubber
    assert "http://" not in text and "https://" not in text  # self-contained
    # the tool reports the saved path + a summary
    assert result.data["path"] == str(out.resolve())
    assert result.data["n_frames"] == 5
