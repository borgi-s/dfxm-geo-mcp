"""run_forward can write the preview PNG to a file (for file-based clients).

Inline MCP image content renders in Claude Desktop but NOT in file-oriented
clients like Cowork, which surface files written into the connected working
folder. Passing output_path makes run_forward write the PNG there so those
clients can display it; omitting it keeps the inline-image default.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_writes_png_when_output_path_given(tmp_path) -> None:
    out = tmp_path / "nested" / "preview.png"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_forward", {"toml_text": "", "output_path": str(out)}
        )

    assert out.exists(), "run_forward did not write the PNG to output_path"
    assert out.read_bytes()[:8] == _PNG_MAGIC
    assert result.data["saved_to"] == str(out.resolve())


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_appends_png_suffix_when_missing(tmp_path) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_forward", {"toml_text": "", "output_path": str(tmp_path / "img")}
        )

    written = tmp_path / "img.png"
    assert written.exists()
    assert result.data["saved_to"] == str(written.resolve())
