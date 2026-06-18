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
