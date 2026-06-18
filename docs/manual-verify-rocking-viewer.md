# Manual verification — self-contained HTML deliverables

Both `run_forward` and `run_rocking` write a **self-contained** `.html` (image(s)
embedded as `data:` URIs, all CSS/JS inline, no external origins). The file opens
full-size in any browser and is surfaced by file-showing clients (Cowork),
sidestepping the inline MCP-Apps widget's `</>` tool-card burial in Claude Desktop.

## Generate the deliverables

```python
# venv: C:/Users/borgi/Documents/dfxm-geo-mcp/.venv/Scripts/python.exe
import base64
from dfxm_geo_mcp.ops import forward as F, rocking as R
from dfxm_geo_mcp.ops.scaffold import scaffold_config
from dfxm_geo_mcp.ui import forward_html as H

# Static single-frame preview (weak-beam default condition).
fr = F.run_forward(scaffold_config(beam="weak"))
m = dict(fr.meta or {}); m["wall_s"] = fr.stats["wall_s"]
open("preview.html", "w", encoding="utf-8").write(
    H.build_static_html(base64.b64encode(fr.png_bytes).decode(), m))

# Interactive φ rocking-curve viewer (21 frames over [-6e-4, 6e-4] rad).
rk = R.run_rocking("", n_frames=21, phi_max=6e-4)
b64 = [base64.b64encode(p).decode() for p in rk.frames_png]
open("rocking.html", "w", encoding="utf-8").write(
    H.build_rocking_html(b64, rk.phis, rk.intensities, rk.meta))
```

Via the MCP tools instead: call `run_forward` (writes `<stem>.png` + `<stem>.html`)
or `run_rocking` (writes the interactive `.html`); both report the saved path.

## Open it

Browser extensions / MCP browser tools often refuse `file://` and `data:` URLs.
To view over HTTP:

```bash
cd <folder-with-the-html>
python -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/rocking.html
```

## What to confirm (interactive viewer)

Verified 2026-06-18 (Al 111 @ 17 keV, 21 frames, φ ∈ [−6e−4, +6e−4] rad):

- **Default view is one end of the curve** — the scrubber starts at index 0
  (`φ = −6.0e−4`, frame 1/21), a weak-beam tail: a dark field. (User directive:
  default starts at one end, consistent with weak being the default.)
- **Scrubbing swaps frames** — drag to the center (index 10, `φ = 0`): the field
  brightens (on-Bragg) and the dark dislocation appears (extinction contrast).
- **The rocking curve tracks** — the blue marker (vertical line + dot) follows the
  scrubber along the intensity-vs-φ polyline; it sits at the low tail at index 0
  and at the peak at index 10. Peak/tail integrated-intensity ratio ≈ 7.
- **Shared color scale** — all frames share one `vmin/vmax`, so brightness genuinely
  changes across the scan (the rocking is visible in the images, not normalized away).
- **Self-contained** — loads with no network; `http://` / `https://` appear nowhere
  in the file.
