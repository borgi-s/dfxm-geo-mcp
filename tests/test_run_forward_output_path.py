"""run_forward always writes the preview PNG to a file and reports the path.

Claude clients (Desktop, claude.ai/Cowork) do NOT render inline MCP tool image
content blocks — the model sees the image but the user never does (a known
client limitation). So run_forward writes the PNG to a real file the user can
open and reports that path in a text block; the inline image is also attached
for any client that does render it.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _text_blocks(result) -> list[str]:
    return [c.text for c in result.content if getattr(c, "type", None) == "text"]


def _has_image(result) -> bool:
    return any(getattr(c, "type", None) == "image" for c in result.content)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_writes_png_and_reports_path_with_output_path(tmp_path) -> None:
    out = tmp_path / "nested" / "preview.png"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_forward", {"toml_text": "", "output_path": str(out)}
        )

    assert out.exists(), "run_forward did not write the PNG to output_path"
    assert out.read_bytes()[:8] == _PNG_MAGIC
    assert _has_image(result)  # inline image still attached
    assert any(str(out.resolve()) in t for t in _text_blocks(result)), (
        "the saved path was not reported in a text block"
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_appends_png_suffix_when_missing(tmp_path) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_forward", {"toml_text": "", "output_path": str(tmp_path / "img")}
        )

    written = tmp_path / "img.png"
    assert written.exists()
    assert any(str(written.resolve()) in t for t in _text_blocks(result))


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_writes_self_contained_html_next_to_png(tmp_path) -> None:
    out = tmp_path / "preview.png"
    async with Client(mcp) as client:
        result = await client.call_tool("run_forward", {"toml_text": "", "output_path": str(out)})

    html = out.with_suffix(".html")
    assert html.exists(), "run_forward did not write the self-contained HTML next to the PNG"
    text = html.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "data:image/png;base64," in text
    assert "http://" not in text and "https://" not in text  # self-contained
    # The HTML path is reported to the user, too.
    assert any(str(html.resolve()) in t for t in _text_blocks(result))


@pytest.mark.asyncio
@pytest.mark.slow
async def test_run_forward_saves_to_default_when_no_output_path(tmp_path, monkeypatch) -> None:
    from dfxm_geo_mcp import runtime

    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    async with Client(mcp) as client:
        result = await client.call_tool("run_forward", {"toml_text": ""})

    saved = tmp_path / "previews" / "forward_preview.png"
    assert saved.exists(), "no output_path: run_forward did not write the default preview file"
    assert saved.read_bytes()[:8] == _PNG_MAGIC
    assert any(str(saved.resolve()) in t for t in _text_blocks(result))
