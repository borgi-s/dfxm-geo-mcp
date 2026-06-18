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


def _note(stats: dict, saved_path: str, html_path: str | None = None) -> str:
    note = (
        f"DFXM forward preview saved to: {saved_path} "
        f"(shape {tuple(stats['shape'])}, backend {stats['backend']}). "
        "Tell the user this path so they can open the image; it also renders "
        "inline in clients that support MCP Apps (Claude Desktop, ChatGPT)."
    )
    if html_path is not None:
        note += (
            f" A self-contained HTML version (opens full-size in any browser) "
            f"is at: {html_path} — give the user this path too."
        )
    return note


def build_forward_result(
    png_bytes: bytes,
    stats: dict[str, Any],
    saved_path: str,
    *,
    supports_ui: bool,
    html_path: str | None = None,
) -> ToolResult | list[Any]:
    """Shape run_forward's return value for UI-capable vs text-only clients.

    The saved file path is reported in both branches (the caller always writes it).
    """
    note = _note(stats, saved_path, html_path)
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
