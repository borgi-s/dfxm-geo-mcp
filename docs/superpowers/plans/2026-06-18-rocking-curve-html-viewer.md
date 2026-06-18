# Rocking-curve HTML viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a self-contained, client-independent HTML deliverable for `dfxm-geo-mcp` — a static single-frame preview (foundation) and the real target: an interactive φ-rocking-curve viewer (scrubber + live rocking-curve plot) that opens full-size in any browser and is surfaced by Cowork.

**Architecture:** A new presentation module (`ui/forward_html.py`) builds self-contained HTML (image(s) embedded as `data:` URIs, all CSS/JS inline — no external origins). A new data op (`ops/rocking.py`) runs a single-axis φ rocking scan through the existing analytic forward backend, keeps every frame (no max-projection), computes the per-frame integrated-intensity rocking curve and a shared color scale, and renders one PNG per frame. The `run_forward` server tool additionally writes a static `.html` next to its PNG; a new `run_rocking` server tool writes the interactive viewer and reports its path.

**Tech Stack:** Python 3.12, FastMCP 3.4.2, dfxm-geo (editable), matplotlib (Agg), numpy, h5py. HTML/CSS/vanilla-JS (inline SVG for the curve; `<input type=range>` scrubber). pytest / mypy / ruff gates.

## Global Constraints

- **stdio discipline:** the forward sim's stdout/stderr must never reach the real process streams (corrupts JSON-RPC). Reuse the existing `redirect_stdout/redirect_stderr` pattern from `ops/forward.py`. (`tests/test_ops_forward.py::test_run_forward_writes_nothing_to_stdout` guards this.)
- **Self-contained HTML:** NO external origins (no CDN, no remote fonts/scripts). Images embedded as `data:image/png;base64,...`. Inline `<style>`/`<script>` only. Must open from `file://` in any browser.
- **Preview caps stay enforced:** Npixels ≤ 128, Nsub ≤ 1. Rocking frame cap ≤ 41 (separate from the single-frame ≤ 9 cap).
- **Analytic backend forced for previews** (`backend="analytic"`, `beamstop=False`); kernel-free.
- **Frame index 0 is "one end of the rocking curve":** the φ scan is centered on the Bragg peak (`value=0`, `range=phi_max`), so `phis[0] == -phi_max` (a weak-beam tail). The interactive viewer's scrubber initializes at index 0 (user directive: default view starts at one end, consistent with weak being the default).
- **Scan-axis contract (dfxm-geo):** a scanned axis is `np.linspace(value - range, value + range, steps)`; `range > 0`, `steps ≥ 2`. φ rocking uses only `[scan.phi]` scanned (all other axes fixed) so frame ordering is a plain ascending linspace.
- **Gates:** `pytest -q` green, `mypy src/dfxm_geo_mcp/` 0 errors, `ruff check` clean before merge.

## File Structure

- **Create** `src/dfxm_geo_mcp/ui/forward_html.py` — `build_static_html` + `build_rocking_html` (self-contained HTML builders). Pure functions, no I/O.
- **Create** `src/dfxm_geo_mcp/ops/rocking.py` — `run_rocking` (φ rocking-scan data op) + `ROCKING_CAPS`. Imports shared render helpers from `ops/forward.py`.
- **Modify** `src/dfxm_geo_mcp/ops/types.py` — add `meta` field to `ForwardResult`; add `RockingResult`.
- **Modify** `src/dfxm_geo_mcp/ops/forward.py` — `_render_png` gains `vmin`/`vmax`; `run_forward` populates `ForwardResult.meta`; factor a `_preview_meta` helper.
- **Modify** `src/dfxm_geo_mcp/server.py` — `run_forward` also writes the static `.html`; add the `run_rocking` tool.
- **Create** `tests/test_ui_forward_html.py`, `tests/test_ops_rocking.py`, `tests/test_server_rocking.py`; extend `tests/test_run_forward_output_path.py`.

---

### Task 1: `_render_png` accepts a shared color scale; `ForwardResult.meta`

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/forward.py` (`_render_png`, `run_forward`)
- Modify: `src/dfxm_geo_mcp/ops/types.py` (`ForwardResult`)
- Test: `tests/test_ops_forward.py`

**Interfaces:**
- Produces: `_render_png(image, *, aspect=1.0, vmin=None, vmax=None) -> bytes` (vmin/vmax default None = autoscale, current behavior). `ForwardResult.meta: dict | None = None`. A `_preview_meta(config, resolved) -> dict` returning `{reflection, energy_keV, backend, shape?, two_theta_deg, phi, beam}`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_ops_forward.py`)

```python
def test_render_png_honours_shared_vmin_vmax():
    import numpy as np
    from dfxm_geo_mcp.ops.forward import _render_png
    img = np.zeros((16, 16))
    img[0, 0] = 1.0
    a = _render_png(img, vmin=0.0, vmax=1.0)
    b = _render_png(img, vmin=0.0, vmax=1000.0)
    assert a[:8] == b"\x89PNG\r\n\x1a\n"
    # A different color scale must change the rendered bytes.
    assert a != b


def test_run_forward_populates_meta():
    res = run_forward("")
    assert res.meta is not None
    assert tuple(res.meta["reflection"]) == (-1, 1, -1)
    assert res.meta["energy_keV"] == 17.0
    assert res.meta["two_theta_deg"] > 0
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_ops_forward.py -k "shared_vmin or populates_meta" -q` → FAIL (TypeError: unexpected kwarg / KeyError meta).

- [ ] **Step 3: Implement**

In `types.py`, add to `ForwardResult`:
```python
    meta: dict | None = None
```

In `forward.py`, change `_render_png` signature/body:
```python
def _render_png(
    image: np.ndarray, *, aspect: float = 1.0, vmin: float | None = None, vmax: float | None = None
) -> bytes:
    fig, axis = plt.subplots(figsize=(4.5, 4.0), dpi=110)
    im = axis.imshow(image, cmap="magma", origin="lower", aspect=aspect, vmin=vmin, vmax=vmax)
    ...
```

Add a meta helper and use it in `run_forward` (after `config` exists and `report.resolved` is known):
```python
def _preview_meta(config: SimulationConfig, resolved: dict | None) -> dict:
    two_theta_deg = math.degrees(2.0 * run_theta(config))
    phi = float(config.scan.phi.value)
    meta: dict = {
        "two_theta_deg": round(two_theta_deg, 4),
        "phi": phi,
        "beam": "strong" if phi == 0.0 else "weak",
    }
    if resolved is not None:
        meta["reflection"] = list(resolved["reflection"])
        meta["energy_keV"] = resolved["energy_keV"]
        meta["backend"] = resolved["backend"]
    return meta
```
Populate it in the returned `ForwardResult` (analytic branch): compute `meta = _preview_meta(config, report.resolved)`, add `meta["shape"] = list(stats["shape"])`, pass `meta=meta` to `ForwardResult(...)`.

- [ ] **Step 4: Run** — `pytest tests/test_ops_forward.py -q` → PASS (existing tests still green).

- [ ] **Step 5: Commit** — `feat: shared vmin/vmax in _render_png + ForwardResult.meta`

---

### Task 2: Static self-contained HTML builder

**Files:**
- Create: `src/dfxm_geo_mcp/ui/forward_html.py`
- Test: `tests/test_ui_forward_html.py`

**Interfaces:**
- Produces: `build_static_html(png_b64: str, meta: dict) -> str`. `meta` keys used (all optional, rendered if present): `reflection`, `energy_keV`, `backend`, `shape`, `two_theta_deg`, `phi`, `beam`, `vmin`, `vmax`, `wall_s`.

- [ ] **Step 1: Write the failing test** (`tests/test_ui_forward_html.py`)

```python
from dfxm_geo_mcp.ui.forward_html import build_static_html


def test_static_html_is_self_contained_and_embeds_image():
    html = build_static_html("QUJD", {"reflection": [-1, 1, -1], "energy_keV": 17.0,
                                       "backend": "analytic", "beam": "weak"})
    assert html.startswith("<!doctype html>")
    assert "data:image/png;base64,QUJD" in html
    # No external origins.
    assert "http://" not in html and "https://" not in html
    # Metadata surfaced.
    assert "analytic" in html
    assert "-1" in html  # reflection rendered
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_ui_forward_html.py -q` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** `src/dfxm_geo_mcp/ui/forward_html.py`

```python
"""Self-contained HTML deliverables for forward previews (image embedded as a
data: URI; all CSS/JS inline; no external origins — opens from file:// anywhere).

Two builders share one shell: build_static_html (single frame + metadata) and
build_rocking_html (multi-frame scrubber + live rocking-curve plot).
"""

from __future__ import annotations

import html as _html
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


def _meta_rows(meta: dict[str, Any]) -> str:
    order = [
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
    rows = []
    for key, label in order:
        if key not in meta or meta[key] is None:
            continue
        val = meta[key]
        text = ", ".join(str(v) for v in val) if isinstance(val, (list, tuple)) else str(val)
        rows.append(f'<tr><td class="k">{_html.escape(label)}</td><td>{_html.escape(text)}</td></tr>')
    return "\n".join(rows)


def build_static_html(png_b64: str, meta: dict[str, Any]) -> str:
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
```

- [ ] **Step 4: Run** — `pytest tests/test_ui_forward_html.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat: self-contained static forward-preview HTML builder`

---

### Task 3: `run_forward` writes the static `.html` next to its PNG

**Files:**
- Modify: `src/dfxm_geo_mcp/server.py` (`run_forward` tool)
- Modify: `src/dfxm_geo_mcp/ui/forward_preview.py` (`build_forward_result` / `_note` mention the html path)
- Test: `tests/test_run_forward_output_path.py`

**Interfaces:**
- Consumes: `forward_html.build_static_html`, `ForwardResult.meta` (Task 1/2).
- Produces: alongside `<stem>.png`, a `<stem>.html`; the returned note text reports both paths.

- [ ] **Step 1: Write the failing test** (append to `tests/test_run_forward_output_path.py`)

```python
def test_run_forward_writes_html_next_to_png(tmp_path):
    from dfxm_geo_mcp.server import run_forward
    out = tmp_path / "preview.png"
    run_forward("", output_path=str(out))
    html = out.with_suffix(".html")
    assert html.exists()
    text = html.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "data:image/png;base64," in text
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_run_forward_output_path.py -k html -q` → FAIL (no .html).

- [ ] **Step 3: Implement**

In `server.py` `run_forward`, after `path.write_bytes(result.png_bytes)` add:
```python
    from dfxm_geo_mcp.ui import forward_html as _html
    html_meta = dict(result.meta or {})
    html_meta.setdefault("shape", list(result.stats["shape"]))
    html_meta.setdefault("backend", result.stats["backend"])
    html_meta["wall_s"] = result.stats["wall_s"]
    html_path = path.with_suffix(".html")
    html_path.write_text(
        _html.build_static_html(_ui._b64(result.png_bytes), html_meta), encoding="utf-8"
    )
```
Thread `str(html_path.resolve())` into `_ui.build_forward_result(..., html_path=...)`; in `forward_preview.py` add `html_path: str | None = None` param and have `_note` append `" Self-contained HTML (opens full-size in any browser): {html_path}."` when set.

- [ ] **Step 4: Run** — `pytest tests/test_run_forward_output_path.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat: run_forward also writes a self-contained static HTML next to the PNG`

---

### Task 4: `RockingResult` + `run_rocking` data op (φ rocking scan, per-frame frames kept)

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/types.py` (`RockingResult`)
- Create: `src/dfxm_geo_mcp/ops/rocking.py`
- Test: `tests/test_ops_rocking.py`

**Interfaces:**
- Consumes: `forward._render_png` (vmin/vmax — Task 1), `forward._pixel_aspect`, `validate_config`, dfxm-geo `SimulationConfig`, `run_theta`, `run_simulation`.
- Produces:
  - `RockingResult(frames_png: list[bytes], phis: list[float], intensities: list[float], vmin: float, vmax: float, meta: dict, bounded: bool = True)`
  - `ROCKING_CAPS = {"max_npixels": 128, "max_nsub": 1, "max_frames": 41}`
  - `run_rocking(toml_text: str, *, n_frames: int = 21, phi_max: float = 6e-4, caps: dict | None = None) -> RockingResult`

- [ ] **Step 1: Write the failing test** (`tests/test_ops_rocking.py`)

```python
import pytest

from dfxm_geo_mcp.ops.rocking import ROCKING_CAPS, run_rocking  # noqa: F401

_TINY = {"max_npixels": 32, "max_nsub": 1, "max_frames": 41}


@pytest.mark.slow
def test_run_rocking_keeps_every_frame_and_traces_a_curve():
    res = run_rocking("", n_frames=5, phi_max=6e-4, caps=_TINY)
    assert len(res.frames_png) == 5
    assert len(res.phis) == 5
    assert len(res.intensities) == 5
    # Centered scan: index 0 is one end (a weak tail), last is the other.
    assert res.phis[0] == pytest.approx(-6e-4)
    assert res.phis[-1] == pytest.approx(6e-4)
    # Every frame is a real PNG with the shared color scale.
    assert all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in res.frames_png)
    assert res.vmax > res.vmin
    # The rocking curve is not flat (φ actually changed the physics).
    assert max(res.intensities) > min(res.intensities)
    assert res.meta["n_frames"] == 5


def test_run_rocking_rejects_over_cap_frames():
    with pytest.raises(ValueError, match="frames"):
        run_rocking("", n_frames=999)


def test_run_rocking_rejects_bad_phi_max():
    with pytest.raises(ValueError):
        run_rocking("", phi_max=0.0)
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_ops_rocking.py -q` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

In `types.py`:
```python
@dataclass(frozen=True)
class RockingResult:
    frames_png: list[bytes]
    phis: list[float]
    intensities: list[float]
    vmin: float
    vmax: float
    meta: dict
    bounded: bool = True
```

Create `src/dfxm_geo_mcp/ops/rocking.py`:
```python
"""run_rocking: a bounded analytic φ rocking scan that keeps every frame.

Unlike run_forward (single frame / max-projected), this runs a centered φ scan
(value=0, range=phi_max) so frame 0 is one weak-beam tail and the last frame is
the other, computes the per-frame integrated-intensity rocking curve, and renders
each frame on a SHARED color scale (so brightness genuinely tracks the curve).
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import math
import tempfile
import time
import tomllib
from pathlib import Path

import h5py
import numpy as np

from dfxm_geo.config import SimulationConfig, run_theta
from dfxm_geo.orchestrator import run_simulation

from dfxm_geo_mcp.ops.forward import _IMAGE_DATASET, _pixel_aspect, _render_png
from dfxm_geo_mcp.ops.types import RockingResult
from dfxm_geo_mcp.ops.validate import validate_config

ROCKING_CAPS = {"max_npixels": 128, "max_nsub": 1, "max_frames": 41}


def run_rocking(
    toml_text: str, *, n_frames: int = 21, phi_max: float = 6e-4, caps: dict | None = None
) -> RockingResult:
    caps = caps if caps is not None else ROCKING_CAPS
    if not 2 <= n_frames <= caps["max_frames"]:
        raise ValueError(
            f"n_frames={n_frames} must be between 2 and the rocking cap "
            f"({caps['max_frames']}). Use the dfxm-forward CLI for larger scans."
        )
    if phi_max <= 0:
        raise ValueError(f"phi_max must be > 0; got {phi_max}")

    report = validate_config(toml_text)
    if not report.ok:
        raise ValueError(report.issues[0].problem)

    raw = tomllib.loads(toml_text)
    user_npixels = raw.get("detector_geometry", {}).get("Npixels")
    if user_npixels is not None and int(user_npixels) > caps["max_npixels"]:
        raise ValueError(
            f"Npixels={user_npixels} exceeds the preview cap ({caps['max_npixels']})."
        )

    with tempfile.TemporaryDirectory() as d:
        cfg_path = Path(d) / "config.toml"
        cfg_path.write_text(toml_text, encoding="utf-8")
        config = SimulationConfig.from_toml(cfg_path)

        if config.detector_geometry.Npixels > caps["max_npixels"]:
            config.detector_geometry = dataclasses.replace(
                config.detector_geometry, Npixels=caps["max_npixels"]
            )
        if config.detector_geometry.Nsub > caps["max_nsub"]:
            config.detector_geometry = dataclasses.replace(
                config.detector_geometry, Nsub=caps["max_nsub"]
            )

        # Single-axis centered φ scan; all other axes fixed.
        phi_axis = dataclasses.replace(config.scan.phi, value=0.0, range=phi_max, steps=n_frames)
        fixed = {
            ax: dataclasses.replace(getattr(config.scan, ax), range=None, steps=None)
            for ax in ("chi", "two_dtheta", "z")
        }
        config.scan = dataclasses.replace(config.scan, phi=phi_axis, **fixed)

        config.reciprocal.backend = "analytic"
        config.reciprocal.beamstop = False

        out_dir = Path(d) / "out"
        t0 = time.perf_counter()
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            run_simulation(config, out_dir)
        wall_s = time.perf_counter() - t0

        with h5py.File(out_dir / "dfxm_geo.h5", "r") as h5:
            frames = np.asarray(h5[_IMAGE_DATASET])

    if frames.ndim != 3 or frames.shape[0] != n_frames:
        raise RuntimeError(f"expected {n_frames} frames, got shape {frames.shape}")

    phis = np.linspace(-phi_max, phi_max, n_frames)
    intensities = frames.sum(axis=(1, 2))
    vmin, vmax = float(frames.min()), float(frames.max())
    aspect = _pixel_aspect(2.0 * run_theta(config))
    frames_png = [_render_png(frames[i], aspect=aspect, vmin=vmin, vmax=vmax) for i in range(n_frames)]

    resolved = report.resolved
    meta = {
        "n_frames": n_frames,
        "phi_max": phi_max,
        "two_theta_deg": round(math.degrees(2.0 * run_theta(config)), 4),
        "shape": [int(frames.shape[1]), int(frames.shape[2])],
        "backend": "analytic",
        "wall_s": round(wall_s, 3),
        "vmin": round(vmin, 6),
        "vmax": round(vmax, 6),
    }
    if resolved is not None:
        meta["reflection"] = list(resolved["reflection"])
        meta["energy_keV"] = resolved["energy_keV"]

    return RockingResult(
        frames_png=frames_png,
        phis=[float(p) for p in phis],
        intensities=[float(v) for v in intensities],
        vmin=vmin,
        vmax=vmax,
        meta=meta,
    )
```

- [ ] **Step 4: Run** — `pytest tests/test_ops_rocking.py -q` → PASS (slow test runs the sim).

- [ ] **Step 5: Commit** — `feat: run_rocking φ-scan data op (per-frame frames + rocking curve + shared scale)`

---

### Task 5: Interactive rocking-curve HTML builder

**Files:**
- Modify: `src/dfxm_geo_mcp/ui/forward_html.py` (`build_rocking_html`)
- Test: `tests/test_ui_forward_html.py`

**Interfaces:**
- Produces: `build_rocking_html(frame_b64s: list[str], phis: list[float], intensities: list[float], meta: dict) -> str`. Embeds a JSON data blob; a `<input type=range>` scrubber (init `value="0"`); an `<img>`; an inline `<svg>` rocking curve with a movable marker. Self-contained.

- [ ] **Step 1: Write the failing test** (append to `tests/test_ui_forward_html.py`)

```python
import json

from dfxm_geo_mcp.ui.forward_html import build_rocking_html


def test_rocking_html_embeds_all_frames_and_inits_at_one_end():
    frames = ["QUJD", "REVG", "R0hJ"]
    phis = [-6e-4, 0.0, 6e-4]
    intens = [10.0, 50.0, 12.0]
    html = build_rocking_html(frames, phis, intens, {"reflection": [-1, 1, -1], "n_frames": 3})
    assert html.startswith("<!doctype html>")
    # all frames embedded
    for b in frames:
        assert b in html
    # scrubber over 0..N-1, initialized at one end (index 0)
    assert 'type="range"' in html
    assert 'max="2"' in html
    assert 'value="0"' in html
    # curve + data present, no external origins
    assert "<svg" in html
    assert "http://" not in html and "https://" not in html
    # embedded data round-trips
    start = html.index('id="dfxm-data"')
    blob = html[html.index(">", start) + 1 : html.index("</script>", start)]
    data = json.loads(blob)
    assert data["phis"] == phis
    assert data["intensities"] == intens
    assert len(data["frames"]) == 3
    assert data["start"] == 0
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_ui_forward_html.py -k rocking -q` → FAIL (no attribute).

- [ ] **Step 3: Implement** — append to `ui/forward_html.py`:

```python
def build_rocking_html(
    frame_b64s: list[str],
    phis: list[float],
    intensities: list[float],
    meta: dict[str, Any],
) -> str:
    data = {
        "frames": [f"data:image/png;base64,{b}" for b in frame_b64s],
        "phis": phis,
        "intensities": intensities,
        "start": 0,  # default view = one end of the rocking curve (weak tail)
    }
    blob = json.dumps(data).replace("</", "<\\/")  # guard against </script>
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
      <div class="read">φ = <b id="phi">–</b> rad &nbsp;·&nbsp; frame <b id="idx">1</b>/{n}
          &nbsp;·&nbsp; intensity <b id="val">–</b></div>
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
  var W=420,H=200,P=30, n=D.phis.length;
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
    '<text class="axlabel" x="'+P+'" y="'+(H-8)+'">φ='+x0.toExponential(2)+'</text>'+
    '<text class="axlabel" x="'+(W-P)+'" y="'+(H-8)+'" text-anchor="end">φ='+x1.toExponential(2)+'</text>'+
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
```

- [ ] **Step 4: Run** — `pytest tests/test_ui_forward_html.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat: interactive rocking-curve HTML builder (scrubber + live SVG curve)`

---

### Task 6: `run_rocking` server tool

**Files:**
- Modify: `src/dfxm_geo_mcp/server.py` (new tool + import)
- Test: `tests/test_server_rocking.py`

**Interfaces:**
- Consumes: `ops.rocking.run_rocking`, `forward_html.build_rocking_html`, `runtime.cache_dir`.
- Produces: `run_rocking(toml_text, n_frames=21, phi_max=6e-4, output_path=None) -> dict` returning `{"path", "n_frames", "phi_max", "peak_phi", "intensity_min", "intensity_max"}` and writing a self-contained `.html`.

- [ ] **Step 1: Write the failing test** (`tests/test_server_rocking.py`)

```python
import pytest


@pytest.mark.slow
def test_run_rocking_tool_writes_html(tmp_path):
    from dfxm_geo_mcp.server import run_rocking
    out = tmp_path / "rock.html"
    res = run_rocking("", n_frames=5, phi_max=6e-4, output_path=str(out))
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert text.count("data:image/png;base64,") >= 5
    assert res["path"] == str(out.resolve())
    assert res["n_frames"] == 5
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_server_rocking.py -q` → FAIL (no attribute run_rocking).

- [ ] **Step 3: Implement** — in `server.py`, import `from dfxm_geo_mcp.ops import rocking as _rocking` and `from dfxm_geo_mcp.ui import forward_html as _html`, then:

```python
@mcp.tool(annotations={"title": "Run rocking-curve viewer", "readOnlyHint": True})
def run_rocking(
    toml_text: str,
    n_frames: int = 21,
    phi_max: float = 6e-4,
    output_path: str | None = None,
) -> dict:
    """Run a bounded φ rocking scan and write a self-contained interactive HTML
    viewer (scrubber + live rocking-curve plot) that opens full-size in any browser.

    The viewer defaults to one end of the rocking curve (a weak-beam tail).
    ALWAYS tell the user the saved .html path so they can open it.
    """
    res = _rocking.run_rocking(toml_text, n_frames=n_frames, phi_max=phi_max)
    frame_b64s = [_ui._b64(p) for p in res.frames_png]
    html = _html.build_rocking_html(frame_b64s, res.phis, res.intensities, res.meta)

    if output_path is not None:
        path = Path(output_path)
        if path.suffix.lower() != ".html":
            path = path.with_suffix(".html")
    else:
        path = runtime.cache_dir() / "previews" / "forward_rocking.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

    peak_i = max(range(len(res.intensities)), key=lambda i: res.intensities[i])
    return {
        "path": str(path.resolve()),
        "n_frames": res.meta["n_frames"],
        "phi_max": phi_max,
        "peak_phi": res.phis[peak_i],
        "intensity_min": min(res.intensities),
        "intensity_max": max(res.intensities),
    }
```

Update `INSTRUCTIONS` to mention `run_rocking` (the interactive viewer; report its .html path).

- [ ] **Step 4: Run** — `pytest tests/test_server_rocking.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat: run_rocking server tool — interactive rocking-curve HTML viewer`

---

### Task 7: Gates + docs + manual-verify note

**Files:**
- Modify: `README.md` (one line: the two HTML outputs)
- Create: `docs/manual-verify-rocking-viewer.md` (how to open the .html, what to look for)

- [ ] **Step 1:** Full gate — `pytest -q` (incl. slow: `pytest -q -m slow`), `mypy src/dfxm_geo_mcp/`, `ruff check`.
- [ ] **Step 2:** Generate a real viewer from a default config; open it; confirm scrubber swaps frames, curve marker tracks, default view at index 0. Record in the manual-verify doc.
- [ ] **Step 3:** Commit docs.

---

## Self-Review

**Spec coverage:**
- #1 static self-contained HTML next to PNG → Tasks 2 + 3. ✓
- Metadata panel (reflection/energy/φ/beam/backend/shape/vmin-vmax) → `_preview_meta` (Task 1) + `_meta_rows` (Task 2). ✓
- #2 interactive viewer: multi-frame embedded, scrubber, rocking-curve plot with current-frame marker → Tasks 4 (data) + 5 (HTML) + 6 (tool). ✓
- Default view starts at one end → `phis[0] == -phi_max` (centered scan, Task 4) + scrubber `value="0"`/`data.start=0` (Task 5). ✓
- Blocker (frame cap ≤9 + max-projection) → bypassed by a separate op `run_rocking` with `ROCKING_CAPS.max_frames=41` and NO max-projection (Task 4). run_forward keeps its single-frame contract intact. ✓
- Client-independent / Cowork-surfaced → saved `.html` file path returned by both tools (Tasks 3, 6). ✓

**Placeholder scan:** none — every code step shows full code.

**Type consistency:** `RockingResult` fields (frames_png/phis/intensities/vmin/vmax/meta) consistent across Tasks 4→6. `build_rocking_html(frame_b64s, phis, intensities, meta)` signature consistent Tasks 5→6. `_render_png(..., vmin, vmax)` consistent Tasks 1→4. `_ui._b64` reused (already in `forward_preview.py`). ✓

## Execution

Per the user's directive ("take us to the goal without any stops"), executing **inline (executing-plans)** in this session with the TDD cycle per task, then a code-review pass before the `--no-ff` merge to `main`. No mid-plan check-ins.
