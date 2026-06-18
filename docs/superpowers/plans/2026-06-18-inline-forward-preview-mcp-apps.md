# Inline forward-preview image via MCP Apps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `run_forward` render its DFXM PNG inline in Claude Desktop and the ChatGPT connector via an official MCP Apps `ui://` template, while always keeping the saved-file-path fallback.

**Architecture:** A new presentation module (`ui/forward_preview.py`) holds the self-contained HTML template, its `ui://` URI, and a pure `build_forward_result(...)` function that shapes the tool return for UI-capable vs text-only clients. `server.py` registers the template as a `ui://` resource, links `run_forward` to it (`app=AppConfig(resource_uri=...)` plus the ChatGPT `openai/outputTemplate` alias), and branches on `ctx.client_supports_extension(UI_EXTENSION_ID)`. The PNG is always written to disk and its path always reported.

**Tech Stack:** Python 3.12, FastMCP 3.4.2 (`fastmcp.apps`: `AppConfig`, `UI_EXTENSION_ID`, `UI_MIME_TYPE`), `mcp.types` (`ImageContent`, `TextContent`), `fastmcp.tools.tool.ToolResult`, pytest + pytest-asyncio.

## Global Constraints

- Python interpreter: `C:\Users\borgi\Documents\dfxm-geo-mcp\.venv\Scripts\python.exe` (run pytest/mypy/ruff with it).
- mypy stays clean on `src/dfxm_geo_mcp/`.
- ruff stays clean (no unused imports — remove `Image` from `server.py` once it moves to the new module).
- **stdio-safety:** never write to real stdout/stderr at import or call time (the JSON-RPC channel lives on stdout). New code must not `print()` or log to stdout.
- The PNG is ALWAYS saved to a file and its absolute path ALWAYS reported, in both the UI and legacy branches.
- The UI template is fully self-contained: inline CSS + JS only, **no external `http(s)://` origins** (so the default CSP suffices — no `ResourceCSP` needed).
- Exact MCP Apps facts (verified in the venv): `UI_EXTENSION_ID = "io.modelcontextprotocol/ui"`; `UI_MIME_TYPE = "text/html;profile=mcp-app"`; a tool with `app=AppConfig(resource_uri=U)` + `meta={"openai/outputTemplate": U}` exposes `tool.meta == {"openai/outputTemplate": U, "ui": {"resourceUri": U}, "fastmcp": {...}}`; resources must NOT pass `resource_uri` (raises).

---

## File Structure

- Create `src/dfxm_geo_mcp/ui/__init__.py` — package marker.
- Create `src/dfxm_geo_mcp/ui/forward_preview.py` — `FORWARD_PREVIEW_URI`, `FORWARD_PREVIEW_HTML`, `build_forward_result(...)`.
- Modify `src/dfxm_geo_mcp/server.py` — register the `ui://` resource; add `app=`/`meta=` + `ctx` to `run_forward`; delegate return shaping to the new module; update `INSTRUCTIONS`; drop the now-unused `Image` import.
- Create `tests/test_ui_forward_preview.py` — pure unit tests for the presentation module.
- Create `tests/test_server_inline_preview.py` — integration tests through `fastmcp.Client`.
- Create `docs/manual-verify-inline-preview.md` — the irreducible manual client test.

---

## Task 1: Presentation module (template + result builder)

**Files:**
- Create: `src/dfxm_geo_mcp/ui/__init__.py`
- Create: `src/dfxm_geo_mcp/ui/forward_preview.py`
- Test: `tests/test_ui_forward_preview.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Uses `fastmcp.utilities.types.Image`, `mcp.types.ImageContent`/`TextContent`, `fastmcp.tools.tool.ToolResult`.
- Produces:
  - `FORWARD_PREVIEW_URI: str = "ui://dfxm-geo/forward-preview.html"`
  - `FORWARD_PREVIEW_HTML: str` (self-contained HTML)
  - `build_forward_result(png_bytes: bytes, stats: dict, saved_path: str, *, supports_ui: bool) -> ToolResult | list[Any]`
    - `supports_ui=False` → `[Image(data=png_bytes, format="png"), note_str]` (today's exact shape)
    - `supports_ui=True` → `ToolResult(content=[ImageContent, TextContent(note)], structured_content={"shape","backend","path"}, meta={"image": {"data","mimeType"}, "caption"})`

- [ ] **Step 1: Create the package marker**

Create `src/dfxm_geo_mcp/ui/__init__.py`:

```python
"""Presentation helpers for MCP tool results (UI templates, result shaping)."""
```

- [ ] **Step 2: Write the failing unit tests**

Create `tests/test_ui_forward_preview.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_forward_preview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dfxm_geo_mcp.ui.forward_preview'`.

- [ ] **Step 4: Implement the module**

Create `src/dfxm_geo_mcp/ui/forward_preview.py`:

```python
"""run_forward presentation: the MCP Apps UI template + tool-result builder.

Renders the forward-preview PNG inline in MCP-Apps-capable clients (Claude
Desktop, ChatGPT connector) via a ui:// HTML template, and falls back to the
saved-file path + inline image block for clients without UI support.
"""

from __future__ import annotations

import base64
from typing import Any

from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import ImageContent, TextContent

FORWARD_PREVIEW_URI = "ui://dfxm-geo/forward-preview.html"

# Self-contained: inline CSS + JS, NO external origins (default CSP suffices).
# The script reads the per-call image from whichever surface the host provides:
#   - ChatGPT Apps SDK: window.openai (toolResponseMetadata / toolOutput)
#   - MCP Apps bridge:   ui/notifications/tool-result postMessage (content[] / _meta)
FORWARD_PREVIEW_HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><style>
  body{margin:0;background:#0b0b0f;color:#e8e8ea;font:13px/1.4 system-ui,sans-serif}
  .wrap{padding:10px}
  img{max-width:100%;height:auto;display:block;border-radius:6px;background:#000}
  .cap{margin-top:6px;color:#9aa;font-size:12px}
  .miss{padding:16px;color:#caa;display:none}
</style></head>
<body>
  <div class="wrap">
    <img id="img" alt="DFXM forward preview" style="display:none">
    <div id="cap" class="cap"></div>
    <div id="miss" class="miss">Image not delivered to this view - open the saved file path reported in the chat.</div>
  </div>
  <script>
    function show(dataUri, caption){
      var img=document.getElementById('img');
      img.src=dataUri; img.style.display='block';
      document.getElementById('cap').textContent=caption||'';
      document.getElementById('miss').style.display='none';
    }
    function toDataUri(img){
      if(!img||!img.data) return null;
      return 'data:'+(img.mimeType||'image/png')+';base64,'+img.data;
    }
    function fromContent(content){
      if(!Array.isArray(content)) return null;
      for(var i=0;i<content.length;i++){
        if(content[i] && content[i].type==='image') return content[i];
      }
      return null;
    }
    function tryRender(payload){
      if(!payload) return false;
      var meta = payload.meta || payload._meta || {};
      var img = meta.image || fromContent(payload.content);
      var uri = toDataUri(img);
      if(!uri) return false;
      show(uri, meta.caption || '');
      return true;
    }
    function pollOpenAI(){
      var oa=window.openai;
      if(!oa) return false;
      return tryRender({meta:(oa.toolResponseMetadata||{}),
                        content:(oa.toolOutput && oa.toolOutput.content)});
    }
    window.addEventListener('openai:set_globals', pollOpenAI);
    window.addEventListener('message', function(ev){
      var m=(ev && ev.data) || {};
      if(m.method==='ui/notifications/tool-result' && m.params) tryRender(m.params);
    });
    pollOpenAI();
    setTimeout(function(){
      if(document.getElementById('img').style.display==='none'){
        document.getElementById('miss').style.display='block';
      }
    }, 1500);
  </script>
</body>
</html>
"""


def _b64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _note(stats: dict, saved_path: str) -> str:
    return (
        f"DFXM forward preview saved to: {saved_path} "
        f"(shape {tuple(stats['shape'])}, backend {stats['backend']}). "
        "Tell the user this path so they can open the image; it also renders "
        "inline in clients that support MCP Apps (Claude Desktop, ChatGPT)."
    )


def build_forward_result(
    png_bytes: bytes, stats: dict, saved_path: str, *, supports_ui: bool
) -> ToolResult | list[Any]:
    """Shape run_forward's return value for UI-capable vs text-only clients.

    The saved file path is reported in both branches (the caller always writes it).
    """
    note = _note(stats, saved_path)
    if not supports_ui:
        return [Image(data=png_bytes, format="png"), note]

    b64 = _b64(png_bytes)
    caption = f"DFXM forward preview - shape {tuple(stats['shape'])} - backend {stats['backend']}"
    return ToolResult(
        content=[
            ImageContent(type="image", data=b64, mimeType="image/png"),
            TextContent(type="text", text=note),
        ],
        structured_content={
            "shape": [int(s) for s in stats["shape"]],
            "backend": stats["backend"],
            "path": saved_path,
        },
        meta={"image": {"data": b64, "mimeType": "image/png"}, "caption": caption},
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_forward_preview.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Type-check the new module**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/ui/forward_preview.py`
Expected: `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add src/dfxm_geo_mcp/ui/__init__.py src/dfxm_geo_mcp/ui/forward_preview.py tests/test_ui_forward_preview.py
git commit -m "feat: forward-preview MCP Apps template + result builder"
```

---

## Task 2: Wire the template and capability branch into the server

**Files:**
- Modify: `src/dfxm_geo_mcp/server.py`
- Test: `tests/test_server_inline_preview.py`

**Interfaces:**
- Consumes (from Task 1): `forward_preview.FORWARD_PREVIEW_URI`, `forward_preview.FORWARD_PREVIEW_HTML`, `forward_preview.build_forward_result(...)`.
- Produces: a registered resource at `ui://dfxm-geo/forward-preview.html` (mime `text/html;profile=mcp-app`); `run_forward` tool meta carrying `meta["ui"]["resourceUri"]` and `meta["openai/outputTemplate"]`, both equal to the URI; UI/legacy return branch selected by `ctx.client_supports_extension(UI_EXTENSION_ID)`.

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_server_inline_preview.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_inline_preview.py -v -m "not slow"`
Expected: FAIL — resource not found / `KeyError: 'openai/outputTemplate'` (wiring absent).

- [ ] **Step 3: Add imports to `server.py`**

In `src/dfxm_geo_mcp/server.py`, replace the import block:

```python
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
```

with:

```python
from fastmcp import Context, FastMCP
from fastmcp.apps import UI_EXTENSION_ID, AppConfig
```

and add to the ops/knowledge import group:

```python
from dfxm_geo_mcp.ui import forward_preview as _ui
```

(The `Image` import is removed — it now lives in `ui/forward_preview.py`. `Path` stays.)

- [ ] **Step 4: Register the UI resource**

Add near the other `@mcp.resource(...)` registrations in `server.py`:

```python
@mcp.resource(_ui.FORWARD_PREVIEW_URI)
def forward_preview_view() -> str:
    """HTML view that renders run_forward's PNG inline (MCP Apps / ChatGPT widget)."""
    return _ui.FORWARD_PREVIEW_HTML
```

- [ ] **Step 5: Link the tool and branch on capability**

Replace the `run_forward` decorator + function (the `@mcp.tool(... output_schema=None)` block and its body) with:

```python
@mcp.tool(
    annotations={"title": "Run forward preview", "readOnlyHint": True},
    # No declared output schema: returns image+text content blocks (or a ToolResult)
    # on success and a structured dict only for the needs-bootstrap case.
    output_schema=None,
    app=AppConfig(resource_uri=_ui.FORWARD_PREVIEW_URI),
    # FastMCP emits only the official io.modelcontextprotocol/ui meta; add the
    # ChatGPT Apps SDK alias by hand so the connector also links the template.
    meta={"openai/outputTemplate": _ui.FORWARD_PREVIEW_URI},
)
def run_forward(
    toml_text: str,
    fidelity: str = "preview",
    output_path: str | None = None,
    ctx: Context | None = None,
) -> list | dict:
    """Run a preview-scale forward simulation, save the DFXM image to a file, and
    return it.

    The rendered PNG is ALWAYS written to a file and its path reported. In clients
    that support MCP Apps (Claude Desktop, ChatGPT connector) the image also renders
    inline via a ui:// template; other clients (Cowork, Claude Code) get the saved
    path plus an inline image content block. Pass ``output_path`` to choose where
    the file is written (a ``.png`` suffix is added if missing).

    ALWAYS tell the user the saved file path so they can open the image.

    For fidelity='mc' with no cached kernel, returns a structured needs-bootstrap
    hint instead.
    """
    result = _forward.run_forward(toml_text, fidelity=fidelity)
    if result.needs_bootstrap:
        return {"needs_bootstrap": True, **(result.bootstrap_hint or {})}

    if output_path is not None:
        path = Path(output_path)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
    else:
        path = runtime.cache_dir() / "previews" / "forward_preview.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.png_bytes)

    supports_ui = False
    if ctx is not None:
        try:
            supports_ui = ctx.client_supports_extension(UI_EXTENSION_ID)
        except Exception:
            supports_ui = False

    return _ui.build_forward_result(
        result.png_bytes, result.stats, str(path.resolve()), supports_ui=supports_ui
    )
```

Note: the declared return annotation stays `list | dict` (FastMCP accepts a `ToolResult` return regardless; `output_schema=None` means no schema is derived from the annotation). Do not import `ToolResult` into `server.py` just for typing — the union return is intentionally loose here.

- [ ] **Step 6: Update the `INSTRUCTIONS` string**

In `server.py`, replace the trailing inline-image sentence of `INSTRUCTIONS`:

```python
    "Previews are capped "
    "(Npixels<=128, <=9 frames); production runs use the dfxm-forward CLI. "
    "run_forward saves the rendered image to a file and reports its path; Claude "
    "does NOT render inline tool images, so ALWAYS give the user that saved path "
    "so they can open it. Pass run_forward's output_path (a .png in the user's "
    "working folder, e.g. the Cowork files folder) to control where it is written."
```

with:

```python
    "Previews are capped "
    "(Npixels<=128, <=9 frames); production runs use the dfxm-forward CLI. "
    "run_forward renders the image inline where the client supports MCP Apps "
    "(Claude Desktop, ChatGPT connector) and ALWAYS also saves the PNG to a file "
    "and reports its path; ALWAYS give the user that saved path so they can open "
    "it even if inline rendering fails. Pass run_forward's output_path (a .png in "
    "the user's working folder, e.g. the Cowork files folder) to control where it "
    "is written."
```

- [ ] **Step 7: Run the new integration tests (incl. slow)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_inline_preview.py -v`
Expected: PASS (3 passed). The slow test runs a real analytic forward sim.

- [ ] **Step 8: Run the full suite + mypy + ruff (no regressions)**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass (existing `test_server_integration.py` / `test_run_forward_output_path.py` still green — the default text-only branch is unchanged).

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/`
Expected: `Success: no issues found`.

Run: `.venv/Scripts/python.exe -m ruff check src/dfxm_geo_mcp/ tests/`
Expected: `All checks passed!` (confirms the `Image` import was removed cleanly).

- [ ] **Step 9: Commit**

```bash
git add src/dfxm_geo_mcp/server.py tests/test_server_inline_preview.py
git commit -m "feat: link run_forward to a ui:// template for inline rendering (Claude Desktop + ChatGPT)"
```

---

## Task 3: Manual-verification doc

**Files:**
- Create: `docs/manual-verify-inline-preview.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: a checklist the user runs in real clients (the irreducible test — inline rendering depends on client behavior and cannot be asserted in pytest).

- [ ] **Step 1: Write the manual-verification doc**

Create `docs/manual-verify-inline-preview.md`:

```markdown
# Manual verification — inline forward preview

Automated tests prove the wiring (resource registered, tool meta links the
template, the UI branch returns the image in `content` + `_meta`). Whether the
image actually *renders inline* depends on the client and must be checked by
hand. The saved-file path is the guaranteed fallback in every case.

## Claude Desktop (local stdio)

1. Point Claude Desktop's MCP config at this server (the `dfxm-geo-mcp` command).
2. Ask: "run a forward preview for the default config and save it to my Desktop".
3. Expected (best case): the DFXM image renders inline in the chat.
4. Known upstream bug (ext-apps #671 / claude-ai-mcp #61): Claude may report
   success but show nothing. If so, the chat still reports the saved `.png`
   path — open that file directly from your filesystem (the server wrote it
   locally). This is the expected degraded behavior, not a regression.

## ChatGPT connector (remote MCP)

1. Add the server as a remote MCP connector in ChatGPT.
2. Ask for a forward preview.
3. Expected: the widget (ui:// template) renders the image inline via the
   `openai/outputTemplate` link.
4. If it does not render, the saved-path text is still returned.

## What "wired correctly" looks like (already covered by pytest)

- `list_resources()` includes `ui://dfxm-geo/forward-preview.html`
  (mime `text/html;profile=mcp-app`).
- `run_forward` tool meta has `ui.resourceUri` and `openai/outputTemplate`
  both pointing at that URI.
- With a UI-capable client, the tool result carries the PNG base64 in both the
  image content block and `_meta.image`.

## If inline rendering fails in both clients

The template's multi-path reader (window.openai vs ui/notifications/tool-result)
is the most likely culprit. Capture which client and what (if anything) appears,
then revisit the JS access paths in `src/dfxm_geo_mcp/ui/forward_preview.py`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/manual-verify-inline-preview.md
git commit -m "docs: manual-verification checklist for inline forward preview"
```

---

## Self-review notes (for the executor)

- **Spec coverage:** UI resource (Task 2 Step 4); tool link + ChatGPT alias (Task 2 Step 5); dual data delivery / capability gating (Task 1 `build_forward_result` + Task 2 Step 5); always-save fallback (Task 2 Step 5, unchanged save logic); unit + integration + manual tests (Tasks 1–3); no-external-origin CSP assumption guarded (Task 1 test).
- **Out of scope (per spec):** interactive scrubber/contrast; multi-frame plumbing; `needs_bootstrap` path (left byte-identical); any tool other than `run_forward`.
- **Risk owned by the manual test (Task 3):** Claude Desktop may still not render (client bug); ChatGPT is the likelier win; possible Claude double-render (native ImageContent + iframe) is cosmetic and tuned here if observed.
