"""Self-contained HTML deliverables for forward previews.

The image(s) are embedded as ``data:`` URIs and all CSS/JS is inline — NO
external origins — so the file opens full-size from ``file://`` in any browser
and is surfaced by clients (Cowork) that show saved files. This sidesteps the
``</>`` tool-card burial of the inline MCP-Apps widget.

Two builders share one shell:
  * ``build_static_html``  — a single frame + a run-metadata panel.
  * ``build_rocking_html`` — a multi-frame φ scan: a scrubber, a live SVG
    rocking-curve plot with a movable marker, and the metadata panel. The
    scrubber initializes at index 0 (one end of the rocking curve — a weak-beam
    tail), per the default-weak convention.
"""

from __future__ import annotations

import html as _htmllib
import json
from typing import Any

_CSS = """
  body{margin:0;background:#0b0b0f;color:#e8e8ea;font:14px/1.5 system-ui,-apple-system,sans-serif}
  .wrap{max-width:980px;margin:0 auto;padding:20px}
  h1{font-size:16px;font-weight:600;margin:0 0 12px;color:#fafafa}
  .panel{display:flex;flex-wrap:wrap;gap:20px}
  .col{flex:1 1 360px;min-width:320px}
  img{max-width:100%;height:auto;display:block;border-radius:8px;background:#000}
  table{border-collapse:collapse;font-size:13px;margin-top:8px}
  td{padding:2px 10px 2px 0;color:#bfc4cc}
  td.k{color:#8a90a0}
  .scrub{width:100%;margin:12px 0 4px}
  .read{font-variant-numeric:tabular-nums;color:#cdd2da}
  .read b{color:#fff}
  svg{width:100%;height:auto;background:#101018;border-radius:8px}
  .axlabel{fill:#8a90a0;font-size:11px}
"""

# Surface order + human labels for the metadata panel (only present keys render).
_META_ORDER: list[tuple[str, str]] = [
    ("reflection", "reflection (hkl)"),
    ("energy_keV", "energy (keV)"),
    ("two_theta_deg", "2θ (deg)"),
    ("beam", "beam condition"),
    ("phi", "φ offset (rad)"),
    ("backend", "backend"),
    ("shape", "image shape (px)"),
    ("n_frames", "frames"),
    ("phi_max", "φ half-range (rad)"),
    ("vmin", "intensity min"),
    ("vmax", "intensity max"),
    ("wall_s", "wall time (s)"),
]


def _meta_rows(meta: dict[str, Any]) -> str:
    rows = []
    for key, label in _META_ORDER:
        if key not in meta or meta[key] is None:
            continue
        val = meta[key]
        text = ", ".join(str(v) for v in val) if isinstance(val, (list, tuple)) else str(val)
        rows.append(
            f'<tr><td class="k">{_htmllib.escape(label)}</td>'
            f"<td>{_htmllib.escape(text)}</td></tr>"
        )
    return "\n".join(rows)


def build_static_html(png_b64: str, meta: dict[str, Any]) -> str:
    """A self-contained single-frame preview: embedded PNG + metadata table."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DFXM forward preview</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <h1>DFXM forward preview</h1>
  <div class="panel">
    <div class="col"><img alt="DFXM forward preview" src="data:image/png;base64,{png_b64}"></div>
    <div class="col"><table>{_meta_rows(meta)}</table></div>
  </div>
</div></body></html>
"""


def build_rocking_html(
    frame_b64s: list[str],
    phis: list[float],
    intensities: list[float],
    meta: dict[str, Any],
) -> str:
    """A self-contained interactive φ-rocking viewer (scrubber + live SVG curve).

    ``frame_b64s[i]`` is the base64 PNG at φ = ``phis[i]``; ``intensities[i]`` is
    that frame's integrated intensity (the rocking curve). The viewer starts at
    index 0 (one end of the curve).
    """
    data = {
        "frames": [f"data:image/png;base64,{b}" for b in frame_b64s],
        "phis": phis,
        "intensities": intensities,
        "start": 0,  # default view = one end of the rocking curve (weak tail)
    }
    blob = json.dumps(data).replace("</", "<\\/")  # guard against a literal </script>
    n = len(frame_b64s)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DFXM rocking-curve viewer</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <h1>DFXM φ rocking-curve viewer</h1>
  <div class="panel">
    <div class="col">
      <img id="frame" alt="DFXM frame">
      <input id="scrub" class="scrub" type="range" min="0" max="{n - 1}" value="0" step="1">
      <div class="read">φ = <b id="phi">–</b> rad &nbsp;·&nbsp;
          frame <b id="idx">1</b>/{n} &nbsp;·&nbsp; intensity <b id="val">–</b></div>
      <svg id="curve" viewBox="0 0 420 200" preserveAspectRatio="none"></svg>
    </div>
    <div class="col"><table>{_meta_rows(meta)}</table></div>
  </div>
</div>
<script type="application/json" id="dfxm-data">{blob}</script>
<script>
(function(){{
  var D=JSON.parse(document.getElementById('dfxm-data').textContent);
  var img=document.getElementById('frame'), sc=document.getElementById('scrub');
  var W=420,H=200,P=30;
  var xs=D.phis, ys=D.intensities;
  var x0=Math.min.apply(null,xs), x1=Math.max.apply(null,xs);
  var y0=Math.min.apply(null,ys), y1=Math.max.apply(null,ys);
  function fx(x){{return P+(W-2*P)*((x-x0)/((x1-x0)||1));}}
  function fy(y){{return (H-P)-(H-2*P)*((y-y0)/((y1-y0)||1));}}
  var pts=xs.map(function(x,i){{return fx(x)+','+fy(ys[i]);}}).join(' ');
  var svg=document.getElementById('curve');
  svg.innerHTML=
    '<polyline fill="none" stroke="#e0457b" stroke-width="2" points="'+pts+'"/>'+
    '<line id="mk" stroke="#7fd1ff" stroke-width="1.5" y1="'+P+'" y2="'+(H-P)+'"/>'+
    '<circle id="dot" r="4" fill="#7fd1ff"/>'+
    '<text class="axlabel" x="'+P+'" y="'+(H-8)+'">phi='+x0.toExponential(2)+'</text>'+
    '<text class="axlabel" x="'+(W-P)+'" y="'+(H-8)+'" text-anchor="end">phi='+x1.toExponential(2)+'</text>'+
    '<text class="axlabel" x="6" y="'+(P+4)+'">I max</text>';
  function fmt(v){{return (Math.abs(v)<1e-2||Math.abs(v)>=1e4)?v.toExponential(3):v.toFixed(3);}}
  function render(i){{
    img.src=D.frames[i];
    document.getElementById('phi').textContent=xs[i].toExponential(4);
    document.getElementById('idx').textContent=(i+1);
    document.getElementById('val').textContent=fmt(ys[i]);
    var mx=fx(xs[i]), my=fy(ys[i]);
    document.getElementById('mk').setAttribute('x1',mx);
    document.getElementById('mk').setAttribute('x2',mx);
    document.getElementById('dot').setAttribute('cx',mx);
    document.getElementById('dot').setAttribute('cy',my);
  }}
  sc.addEventListener('input',function(){{render(+sc.value);}});
  sc.value=D.start; render(D.start);
}})();
</script>
</body></html>
"""
