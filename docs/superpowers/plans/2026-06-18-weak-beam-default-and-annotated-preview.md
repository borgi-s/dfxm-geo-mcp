# Weak-beam default + annotated preview rendering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weak-beam φ condition the default (and controllable) in `scaffold_config`/the MCP tool, and render previews with pixel axes + a colorbar.

**Architecture:** `scaffold_config` gains `beam="weak"` (default) / `"strong"` plus a `phi_offset` override; it emits a single-frame `[scan.phi]` block whenever the effective φ ≠ 0. The MCP `scaffold_config` tool forwards the two params. `_render_png` is reworked to draw pixel-indexed axes and a colorbar. A slow end-to-end test proves weak vs strong produce different images.

**Tech Stack:** Python 3.12, dfxm-geo (`[scan.phi]` via `ScanConfig`/`AxisScanConfig`, radians), FastMCP, matplotlib (Agg), pytest.

## Global Constraints

- Python interpreter: `C:\Users\borgi\Documents\dfxm-geo-mcp\.venv\Scripts\python.exe` (run pytest/mypy/ruff with it). The bare `python` is Python 2.7 — never use it.
- **Weak beam is the default.** A plain `scaffold_config()` MUST emit a `[scan.phi]` block; `beam="strong"` (φ=0) must emit NO `[scan.phi]` block (reproducing today's output exactly).
- φ units are **radians** (config-native). `WEAK_BEAM_PHI_RAD = 1.75e-4`. `f"value = {1.75e-4}"` renders as `value = 0.000175` (verified).
- A `[scan.phi]` block carries `value = <φ>` only — NO `range`/`steps` (single frame; no max-projection).
- Emit the `[scan.phi]` block in EVERY scaffold path (FCC-simplified, FCC-oblique, BCC-cubic-oblique, CIF) — append it to the shared `lines` list so the early FCC-simplified return includes it too.
- mypy clean on `src/dfxm_geo_mcp/`; ruff clean on `src/dfxm_geo_mcp/ tests/`; no writes to real stdout/stderr at import or call time.
- Preview caps and the `needs_bootstrap` path are unchanged; `run_forward` is untouched except `_render_png`'s body.

---

## File Structure

- Modify `src/dfxm_geo_mcp/ops/scaffold.py` — `WEAK_BEAM_PHI_RAD`, `_scan_phi_lines`, `beam`/`phi_offset` params + emit logic.
- Modify `src/dfxm_geo_mcp/server.py` — `scaffold_config` tool gains `beam`/`phi_offset` pass-through; `INSTRUCTIONS` line.
- Modify `src/dfxm_geo_mcp/ops/forward.py` — `_render_png` body (pixel axes + colorbar).
- Modify `tests/test_ops_scaffold.py` — add weak/strong/override/invalid/cross-path unit tests.
- Create `tests/test_weak_beam_e2e.py` — slow weak-vs-strong image-difference test.
- Modify `tests/test_ops_forward.py` — add `_render_png` PNG-validity unit test.
- Modify `tests/test_server_integration.py` — add scaffold-tool weak/strong param tests.

---

## Task 1: Weak-beam knob in `scaffold_config`

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/scaffold.py`
- Test: `tests/test_ops_scaffold.py`, `tests/test_weak_beam_e2e.py` (create)

**Interfaces:**
- Consumes: nothing new (existing `scaffold_config`, `validate_config`, `_forward.run_forward`).
- Produces:
  - `WEAK_BEAM_PHI_RAD: float = 1.75e-4`
  - `_scan_phi_lines(phi: float) -> list[str]` — `[]` when `phi == 0.0`, else `["", "[scan.phi]", f"value = {phi}"]`.
  - `scaffold_config(..., beam: str = "weak", phi_offset: float | None = None) -> str` — emits `[scan.phi]` when effective φ ≠ 0.

- [ ] **Step 1: Write the failing unit tests** — append to `tests/test_ops_scaffold.py`:

```python
def test_default_is_weak_beam():
    toml = scaffold_config()
    assert "[scan.phi]" in toml
    assert "value = 0.000175" in toml
    assert validate_config(toml).ok


def test_strong_beam_emits_no_scan_block():
    toml = scaffold_config(beam="strong")
    assert "[scan.phi]" not in toml
    assert validate_config(toml).ok


def test_phi_offset_overrides_preset():
    toml = scaffold_config(phi_offset=5e-4)
    assert "[scan.phi]" in toml
    assert "value = 0.0005" in toml
    assert validate_config(toml).ok


def test_phi_offset_zero_emits_no_scan_block():
    toml = scaffold_config(phi_offset=0.0)
    assert "[scan.phi]" not in toml


def test_invalid_beam_raises():
    with pytest.raises(ValueError, match="weak"):
        scaffold_config(beam="medium")


def test_weak_beam_present_on_bcc_path():
    toml = scaffold_config(
        material="W", structure_type="bcc", reflection=(1, 1, 0),
        geometry_mode="oblique", energy_keV=17.0,
    )
    assert "[scan.phi]" in toml
    assert validate_config(toml).ok
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_scaffold.py -v`
Expected: the new tests FAIL (default emits no `[scan.phi]`; `beam`/`phi_offset` are unexpected kwargs → `TypeError`).

- [ ] **Step 3: Add the constant and helper** — in `src/dfxm_geo_mcp/ops/scaffold.py`, after the `_LATTICE_A_M` block (around line 31), add:

```python
# Weak-beam rocking offset (radians). The dislocation-contrast condition: a single
# frame at a fixed phi offset off the Bragg peak. This is the value used in the
# dfxm-geo example notebooks; it is APPROXIMATE — the physically correct offset
# scales with the rocking-curve width (reflection/energy/material). Callers needing
# a specific value pass `phi_offset` to scaffold_config.
WEAK_BEAM_PHI_RAD = 1.75e-4


def _scan_phi_lines(phi: float) -> list[str]:
    """TOML lines for a fixed single-frame [scan.phi]; empty when phi == 0.

    A bare `value` (no range/steps) fixes phi at a single frame — no rocking scan,
    so run_forward renders that one frame (no max-projection).
    """
    if phi == 0.0:
        return []
    return ["", "[scan.phi]", f"value = {phi}"]
```

- [ ] **Step 4: Add the params and emit logic** — change the `scaffold_config` signature and body.

Signature (add the two params after `scan_mode`):

```python
def scaffold_config(
    *,
    material: str | None = None,
    structure_type: str | None = None,
    reflection: tuple[int, int, int] | None = None,
    energy_keV: float = 17.0,
    geometry_mode: str = "symmetric",
    cif_path: str | None = None,
    scan_mode: str = "single",
    backend: str = "analytic",
    beam: str = "weak",
    phi_offset: float | None = None,
) -> str:
```

At the top of the body (right after the docstring, before `hkl = reflection or (-1, 1, -1)`), add:

```python
    if beam not in ("weak", "strong"):
        raise ValueError(f"beam must be 'weak' or 'strong', got {beam!r}")
    phi = phi_offset if phi_offset is not None else (WEAK_BEAM_PHI_RAD if beam == "weak" else 0.0)
```

Then append the scan block to `lines` immediately after the `lines = [ ... ]` literal (right after the `beamstop = ...` entry, before the `# FCC symmetric:` comment):

```python
    lines += _scan_phi_lines(phi)
```

(`lines` is returned in the FCC-simplified early return AND combined with `crystal_lines`/`geometry_lines` in the other paths, so appending here covers every path. TOML block order is irrelevant.)

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_scaffold.py -v`
Expected: PASS — all new tests plus the pre-existing ones (the pre-existing tests only assert `validate_config(...).ok`, which still holds with the added `[scan.phi]`).

- [ ] **Step 6: Write the slow end-to-end behavioral test** — create `tests/test_weak_beam_e2e.py`:

```python
"""Weak vs strong beam produce different forward images.

The regression that would have caught the original bug: a phi offset must change
the rendered physics, not be silently ignored. Uses the ops layer directly.
"""

from __future__ import annotations

import pytest

from dfxm_geo_mcp.ops import forward as _forward
from dfxm_geo_mcp.ops.scaffold import scaffold_config

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.slow
def test_weak_and_strong_produce_different_images():
    weak = _forward.run_forward(scaffold_config(beam="weak"))
    strong = _forward.run_forward(scaffold_config(beam="strong"))
    assert weak.png_bytes[:8] == _PNG_MAGIC
    assert strong.png_bytes[:8] == _PNG_MAGIC
    # The phi offset changed the physics: the two renders are not identical.
    assert weak.png_bytes != strong.png_bytes
```

- [ ] **Step 7: Run the slow test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weak_beam_e2e.py -v`
Expected: PASS (runs two real analytic previews; takes longer due to JIT).

- [ ] **Step 8: mypy + ruff**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/ops/scaffold.py`
Expected: `Success: no issues found`.
Run: `.venv/Scripts/python.exe -m ruff check src/dfxm_geo_mcp/ tests/`
Expected: `All checks passed!`.

- [ ] **Step 9: Commit**

```bash
git add src/dfxm_geo_mcp/ops/scaffold.py tests/test_ops_scaffold.py tests/test_weak_beam_e2e.py
git commit -m "feat: weak beam is the default scaffold condition (phi knob + override)"
```

---

## Task 2: Expose `beam`/`phi_offset` on the MCP tool

**Files:**
- Modify: `src/dfxm_geo_mcp/server.py`
- Test: `tests/test_server_integration.py`

**Interfaces:**
- Consumes (from Task 1): `_scaffold.scaffold_config(..., beam=..., phi_offset=...)`.
- Produces: the `scaffold_config` MCP tool accepts `beam` and `phi_offset`; default output carries `[scan.phi]`.

- [ ] **Step 1: Write the failing integration tests** — append to `tests/test_server_integration.py`:

```python
@pytest.mark.asyncio
async def test_scaffold_tool_defaults_to_weak_beam():
    async with Client(mcp) as client:
        result = await client.call_tool("scaffold_config", {})
    assert "[scan.phi]" in result.data


@pytest.mark.asyncio
async def test_scaffold_tool_strong_beam_param_omits_scan_block():
    async with Client(mcp) as client:
        result = await client.call_tool("scaffold_config", {"beam": "strong"})
    assert "[scan.phi]" not in result.data
```

(If `result.data` is not the returned string in this FastMCP version, read it from the first text content block: `result.content[0].text`. Confirm during RED/GREEN and use whichever holds the TOML string.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_integration.py -k scaffold_tool -v`
Expected: FAIL — default currently emits no `[scan.phi]` (Task 1 changed the op, but the tool still passes no `beam`, so the default applies — actually this passes once Task 1 is merged; the strong-param test FAILS because the tool rejects the unknown `beam` kwarg). Confirm both behaviors.

- [ ] **Step 3: Add the params to the tool** — in `src/dfxm_geo_mcp/server.py`, change the `scaffold_config` tool signature and call.

Signature — add `beam` and `phi_offset` after `scan_mode`:

```python
def scaffold_config(
    material: str | None = None,
    structure_type: str | None = None,
    reflection: list[int] | None = None,
    energy_keV: float = 17.0,
    geometry_mode: str = "symmetric",
    cif_path: str | None = None,
    scan_mode: str = "single",
    beam: str = "weak",
    phi_offset: float | None = None,
) -> str:
    """Return a valid starter dfxm-geo config (TOML text) for the requested crystal/reflection.

    Defaults to the WEAK-beam condition (beam="weak": a single frame at a fixed phi
    offset off the Bragg peak — the dislocation-contrast condition). Pass beam="strong"
    for the on-peak (bright-field) condition, or phi_offset (radians) for a specific
    rocking offset that overrides the preset.
    """
    hkl = tuple(reflection) if reflection else None
    return _scaffold.scaffold_config(
        material=material,
        structure_type=structure_type,
        reflection=hkl,  # type: ignore[arg-type]
        energy_keV=energy_keV,
        geometry_mode=geometry_mode,
        cif_path=cif_path,
        scan_mode=scan_mode,
        beam=beam,
        phi_offset=phi_offset,
    )
```

- [ ] **Step 4: Update `INSTRUCTIONS`** — in `server.py`, add one sentence to the `INSTRUCTIONS` string (after the "scaffold_config -> validate_config -> run_forward" sentence):

```python
    "Previews default to the WEAK-beam condition (scaffold_config beam='weak', the "
    "dislocation-contrast condition off the Bragg peak); pass beam='strong' for the "
    "on-peak bright field, or phi_offset (radians) for a specific rocking offset. "
```

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_integration.py -k scaffold_tool -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Full suite + mypy + ruff**

Run: `.venv/Scripts/python.exe -m pytest -q -m "not slow"`
Expected: all pass.
Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/`
Expected: `Success: no issues found`.
Run: `.venv/Scripts/python.exe -m ruff check src/dfxm_geo_mcp/ tests/`
Expected: `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add src/dfxm_geo_mcp/server.py tests/test_server_integration.py
git commit -m "feat: scaffold_config tool exposes beam/phi_offset (weak default)"
```

---

## Task 3: Annotated preview rendering (pixel axes + colorbar)

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/forward.py` (function `_render_png`, currently lines ~40-47)
- Test: `tests/test_ops_forward.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_render_png(image: np.ndarray) -> bytes` (signature unchanged) now renders pixel axes + a colorbar.

- [ ] **Step 1: Write the failing unit test** — append to `tests/test_ops_forward.py`:

```python
def test_render_png_returns_valid_annotated_png():
    import numpy as np

    from dfxm_geo_mcp.ops.forward import _render_png

    img = np.random.default_rng(0).random((32, 32))
    png = _render_png(img)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # A colorbar + axes make the figure non-trivial; guard against an empty render.
    assert len(png) > 2000
```

- [ ] **Step 2: Run the test to verify it passes against the OLD render, then confirm intent**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_forward.py::test_render_png_returns_valid_annotated_png -v`
Expected: this asserts PNG validity only, so it may already PASS against the bare render. That is fine — the visual change (axes + colorbar) is verified manually; this test is a non-empty-PNG guard. Proceed to implement the visual change.

- [ ] **Step 3: Rework `_render_png`** — replace the function body in `src/dfxm_geo_mcp/ops/forward.py`:

```python
def _render_png(image: np.ndarray) -> bytes:
    fig, axis = plt.subplots(figsize=(4.5, 4.0), dpi=110)
    im = axis.imshow(image, cmap="magma", origin="lower")  # default 'equal' aspect: square pixels
    axis.set_xlabel("x (pixels)")
    axis.set_ylabel("y (pixels)")
    cbar = fig.colorbar(im, ax=axis, fraction=0.046, pad=0.04)
    cbar.set_label("intensity (a.u.)")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Run the render test + the existing forward tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_forward.py -v`
Expected: PASS (the new test plus existing forward tests — `_render_png` still returns a valid PNG).

- [ ] **Step 5: mypy + ruff**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/ops/forward.py`
Expected: `Success: no issues found`.
Run: `.venv/Scripts/python.exe -m ruff check src/dfxm_geo_mcp/ tests/`
Expected: `All checks passed!`.

- [ ] **Step 6: Full suite (incl. slow) sanity**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass (the slow weak-vs-strong test renders through the new `_render_png`).

- [ ] **Step 7: Commit**

```bash
git add src/dfxm_geo_mcp/ops/forward.py tests/test_ops_forward.py
git commit -m "feat: annotate forward preview with pixel axes + colorbar"
```

---

## Manual verification (after all tasks)

Re-run a **default** preview in the target client (restart it — editable install). Confirm:
1. Contrast is now weak-beam: a **dark** field with the dislocation region **lit bright** (the inverse of the previous bright-field-with-dark-dot strong-beam image).
2. The image carries **pixel axes** and a **colorbar** showing the intensity range.
3. `beam="strong"` reproduces the previous bright-field image.

## Self-review notes (for the executor)

- **Spec coverage:** weak default (Task 1 emit logic + Task 2 tool default); explicit override (`phi_offset`, Task 1); single-frame `[scan.phi]` (Task 1 `_scan_phi_lines`); emitted on every path (append to `lines`); strong reproduces today (φ=0 → no block); pixel axes + colorbar (Task 3); discoverability via tool + INSTRUCTIONS (Task 2); behavioral guarantee (Task 1 slow e2e); manual visual check (above).
- **Out of scope (per spec):** physical-µm scalebar; multi-frame max-projection change; φ-on-image annotation; interactive HTML rocking-curve view (future).
- **Regression note:** existing `tests/test_ops_scaffold.py` keep passing because they only assert `validate_config(...).ok`, which still holds with the added `[scan.phi]`. No byte-exact scaffold assertion exists to update.
