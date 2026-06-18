# Inline forward-preview image via MCP Apps — design

Date: 2026-06-18
Status: approved (pending written-spec review)

## Problem

`run_forward` returns its DFXM forward-model PNG as an MCP `image` content block
plus a saved-file path. The image does **not** render inline in the two clients
the user cares about:

- **Claude Desktop** renders *nothing* — it reports success but no image appears,
  and its in-chat "download" of the result fails. There is no native image-block
  path to lean on here.
- **ChatGPT connector** (remote MCP) — likewise no reliable inline image from a
  plain `image` block.

(Claude Code, the CLI, already renders inline image blocks — not a target.)

## Goal

Render the forward-preview PNG **inline** in Claude Desktop and the ChatGPT
connector, while never regressing the existing saved-file fallback (the only thing
that works today, and the safety net if inline rendering fails).

Non-goals (YAGNI for this cut): interactive viewer (scan-stack scrubber, contrast
sliders); multi-frame plumbing; any change to the `needs_bootstrap` path; touching
any tool other than `run_forward`.

## Background: why MCP Apps

Both targets implement the **official MCP Apps** extension (announced 2026-01-26),
where a tool links to a `ui://` HTML resource that the host renders in a sandboxed
iframe.

- Claude Desktop & claude.ai: support MCP Apps, but have **open upstream rendering
  bugs** (modelcontextprotocol/ext-apps #671, anthropics/claude-ai-mcp #61: correct
  protocol exchange, still renders plain text). So correct wiring may still not
  render on Desktop — a client bug we cannot fix, only degrade cleanly around.
- ChatGPT Apps SDK: same `ui://` + `_meta` mechanism; honors
  `_meta["openai/outputTemplate"]` as a compat alias to `_meta.ui.resourceUri`.

A plain inline `image` content block is the doc's "option 1" and is already what
ships today — confirmed not to render in either target. A per-call `data:` URI
baked into HTML is appealing but does **not** fit official MCP Apps: a `ui://`
resource is a *static template*, cached by URI; per-call data must be delivered to
the iframe as tool-result data, not embedded in the template.

## FastMCP 3.4.2 API surface (verified in the venv)

`fastmcp.apps` provides: `AppConfig`, `ResourceCSP`, `ResourcePermissions`,
`UI_EXTENSION_ID = "io.modelcontextprotocol/ui"`,
`UI_MIME_TYPE = "text/html;profile=mcp-app"`, `app_config_to_meta_dict`.

- `@mcp.resource(uri, app=AppConfig(...))` — registering a `ui://...` resource;
  FastMCP serves it with mime `text/html;profile=mcp-app` automatically.
- `@mcp.tool(app=AppConfig(resource_uri="ui://..."), meta={...})` — links a tool to
  the template. `AppConfig` fields: `resource_uri`, `visibility`, `csp`,
  `permissions`, `domain`, `prefers_border`.
- **Gap found:** `app_config_to_meta_dict(AppConfig(...))` emits only
  `{"resourceUri": ...}` under the official `io.modelcontextprotocol/ui`
  extension. It does **not** add `openai/outputTemplate`. So the ChatGPT alias must
  be added by hand via the tool's `meta=` kwarg.
- `ctx.client_supports_extension(UI_EXTENSION_ID)` — runtime capability check for
  the fallback gate.

## Architecture — three pieces

### 1. UI resource: `ui://dfxm-geo/forward-preview.html`

A fully self-contained HTML template (inline CSS + JS, **no external domains**, so
the default CSP suffices — no `ResourceCSP` config needed). Contains an empty
`<img>` and a caption slot. Its script reads the tool result and sets
`img.src = "data:image/png;base64,<…>"` plus the caption (shape, backend).

Because the two clients surface tool-result data differently, the script tries
each access path in order and uses the first that yields an image:

1. ChatGPT: `window.openai?.toolResponseMetadata?.image` (the tool `_meta`).
2. MCP Apps bridge: an `ontoolresult`-style callback delivering the `content`
   array; find the `image` block.
3. Generic: a `message` listener for `ui/notifications/tool-result`, reading
   `structuredContent` / `_meta` from the payload.

The template is registered once; its URI is the cache key. If its HTML/JS changes
in a breaking way later, bump the URI (e.g. `…/forward-preview-v2.html`).

### 2. `run_forward` linked to the template

```python
@mcp.tool(
    annotations={"title": "Run forward preview", "readOnlyHint": True},
    output_schema=None,
    app=AppConfig(resource_uri="ui://dfxm-geo/forward-preview.html"),
    meta={"openai/outputTemplate": "ui://dfxm-geo/forward-preview.html"},
)
def run_forward(toml_text, fidelity="preview", output_path=None, ctx: Context = ...):
    ...
```

### 3. Dual data delivery + capability gating

The PNG is **always** saved to disk and its absolute path **always** reported, in
every branch (this is the unconditional fallback — for Desktop the file lands on
the user's own local filesystem, openable directly).

- **`needs_bootstrap`** → unchanged structured dict (no UI).
- **UI supported** (`ctx.client_supports_extension(UI_EXTENSION_ID)` true) → return
  a `ToolResult` with:
  - `content`: `[ImageContent(base64 png), TextContent(caption incl. saved path)]`
    — Claude's bridge hands `content` to the template; the model also "sees" the
    image. (Per user: keep the `ImageContent` even in the UI branch; accept a
    possible Claude double-render as a verify-time tweak, not a blocker.)
  - `_meta`: `{"image": {"data": b64, "mimeType": "image/png"}, "caption": …}` —
    ChatGPT's widget reads `_meta`; keeps base64 out of model-visible
    `structuredContent`.
  - `structuredContent`: `{"shape": …, "backend": …, "path": …}` — small,
    model-visible, no base64 bloat.
- **UI not supported** (incl. Cowork, Claude Code) → today's behavior verbatim:
  save file + `Image(...)` block + path note.

## Components and boundaries

- Keep the template HTML in its own module/asset (e.g.
  `src/dfxm_geo_mcp/ui/forward_preview.py` exposing the HTML string, or a
  `.html` packaged asset) so `server.py` stays a thin registration layer and the
  markup is testable/inspectable on its own.
- `server.py` gains: the `@mcp.resource("ui://…")` registration, the `app=`/`meta=`
  on `run_forward`, and the capability branch. The image-bytes / file-save logic
  already in `run_forward` is reused unchanged.

## Error handling

- If `ctx` is unavailable or `client_supports_extension` raises, treat as
  unsupported and fall through to the legacy file+Image+note path.
- File-save errors propagate as today (the save is the contract).
- Template JS: if no image is found via any access path, show a short "image not
  delivered — open the saved file path" message rather than a blank frame.

## Testing

**Unit (pytest):**
- The `ui://dfxm-geo/forward-preview.html` resource is registered and serves mime
  `text/html;profile=mcp-app`.
- `run_forward`'s tool metadata carries **both** the official
  `io.modelcontextprotocol/ui` `resourceUri` **and** `openai/outputTemplate`,
  pointing at the same URI.
- UI-supported branch (stub context returning `True`): result carries the image in
  both `content` (ImageContent) and `_meta`; `structuredContent` has no base64;
  file is written and path reported.
- UI-unsupported branch (stub returning `False`): legacy `[Image, note]` shape;
  file written.
- `needs_bootstrap` branch unchanged.
- Template HTML is syntactically well-formed and references no external origins
  (guards the no-CSP-config assumption).

**Manual (user, post-merge — the irreducible test):**
- Load the server in Claude Desktop and run a forward preview → confirm inline
  render (or confirm the known Desktop bug and that the saved path still works).
- Same in the ChatGPT connector.
This is the doc's "render behavior is the variable" — wiring can be correct and
Desktop may still not render; the fallback covers that.

## Risks

- **Claude Desktop may still render nothing** (upstream bug). Not fixable here;
  the saved local file path is the guaranteed Desktop path.
- **ChatGPT vs Claude data-surface differences** mean the template's multi-path
  reader is the fragile part — most likely place for a real bug; covered by the
  manual test in both clients.
- Possible **double render** in Claude (native ImageContent + iframe) — cosmetic,
  tuned at verify time.

## Sources

- MCP Apps overview / blog: https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
- Claude Desktop render bug: https://github.com/modelcontextprotocol/ext-apps/issues/671 ;
  https://github.com/anthropics/claude-ai-mcp/issues/61
- ChatGPT Apps SDK MCP server: https://developers.openai.com/apps-sdk/build/mcp-server
- FastMCP custom HTML apps: https://gofastmcp.com/apps/low-level
- Local landscape brief: docs/iaskedaotheratomicgizmo.md
