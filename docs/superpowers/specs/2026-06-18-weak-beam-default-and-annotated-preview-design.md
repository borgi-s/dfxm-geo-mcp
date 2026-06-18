# Weak-beam default + annotated preview rendering — design

Date: 2026-06-18
Status: approved (user-directed: weak beam is the default)

## Problem

A user asked the agent (in another client session) for a "φ weak-beam" DFXM forward
preview and got a **strong-beam** image instead: a bright field with a small dark
dislocation (on-Bragg-peak contrast), not the weak-beam inverse (dark field, lattice
near the dislocation lit bright). Verified by opening the saved preview PNG directly.

Root causes, both in this repo:
1. `scaffold_config`'s `scan_mode` is a **no-op** — it emits no `[scan]` block, so φ
   defaults to `[scan.phi].value = 0.0` (the Bragg peak = strong beam). There is no
   discoverable knob for the weak-beam condition, so the agent could not set it.
2. `run_forward`'s `_render_png` shows a bare image: `axis("off")`, no colorbar, no
   spatial reference — the viewer cannot read intensity range or pixel scale.

(Confirmed: `build_scan_grid` returns `np.array([axis.value])` for a fixed axis, so a
single-frame `[scan.phi] value = X` reaches `fm.forward(..., phi=X)`; the analytic
backend is valid in the weak-beam tails per the dfxm-geo notes, and
`forward_model.py:1057` documents the weak/strong rocking physics. So weak-beam via a
fixed non-zero φ is sound.)

## Goal

1. Make the weak-beam condition the **default** and easily controllable from
   `scaffold_config` (and thus the MCP tool), with an explicit override for a
   specific φ.
2. Render previews with **pixel axes + a colorbar** so size and intensity range are
   legible.

User directive: **weak beam is the default — strong beam is never the default.** A
plain `scaffold_config()` must produce a weak-beam config.

## Non-goals (YAGNI for this cut)

- Physical-µm scalebar (pixel axes were chosen; µm needs detector pitch/magnification).
- Changing `run_forward`'s multi-frame max-projection (weak beam is a single frame, so
  it is unaffected).
- Annotating φ on the image itself.
- **Future (explicitly deferred):** an interactive HTML preview with at least a rocking
  curve, whose default view should start at one end of the rocking curve. Out of scope
  here; recorded so the weak-default choice stays consistent with it.

## Design

### 1. Weak-beam knob in `scaffold_config` (`src/dfxm_geo_mcp/ops/scaffold.py`)

- New parameters:
  - `beam: str = "weak"` — `"weak"` or `"strong"`. **Default `"weak"`.** Invalid values
    raise `ValueError`.
  - `phi_offset: float | None = None` — explicit φ in **radians** (config-native units).
    Overrides the `beam` preset when given.
- Module constant `WEAK_BEAM_PHI_RAD = 1.75e-4` — the weak-beam φ offset (the value used
  in the dfxm-geo example notebooks). Documented as an **approximation**: the physically
  correct offset scales with the rocking-curve width (reflection/energy/material); the
  `phi_offset` override is the escape hatch for a specific value.
- Effective φ:
  - `phi_offset` if it is not `None`,
  - else `WEAK_BEAM_PHI_RAD` if `beam == "weak"`,
  - else `0.0` (`beam == "strong"`).
- Emit a `[scan.phi]` block (`value = <φ>`, no `range`/`steps` → single frame) in **every**
  config path (FCC-simplified, FCC-oblique, BCC-cubic-oblique, CIF) **only when φ ≠ 0.0**.
  Implementation: build the scan lines once and append to the shared `lines` list right
  after the `[reciprocal]` block, so the FCC-simplified early return and the
  crystal/geometry combined return both include it. TOML block order is irrelevant.
  - Consequence: the **default** (weak) config now carries `[scan.phi] value = 0.000175`.
    A `beam="strong"` (or `phi_offset=0.0`) config emits no `[scan.phi]` block — i.e. the
    strong path reproduces today's exact output.

### 2. MCP tool surface (`src/dfxm_geo_mcp/server.py`)

- `scaffold_config` tool gains `beam: str = "weak"` and `phi_offset: float | None = None`
  pass-through parameters; docstring explains weak is the default and `phi_offset` overrides.
- `INSTRUCTIONS` gains one sentence: previews default to the weak-beam condition
  (`beam="weak"`, the dislocation contrast condition); pass `beam="strong"` for on-peak,
  or `phi_offset` for a specific φ. This is the discoverability fix for the root cause.

### 3. Annotated rendering (`_render_png` in `src/dfxm_geo_mcp/ops/forward.py`)

Applies to every preview. Replace the bare-image rendering with:
- Pixel-indexed x/y axes (visible ticks), labels `x (pixels)` and `y (pixels)`, square
  aspect (so pixels are square; drop today's `aspect="auto"`).
- A **colorbar** mapped to the image's value range, labelled `intensity (a.u.)`.
- Keep `cmap="magma"`, `origin="lower"`.
- Return PNG bytes as today (signature unchanged: takes the 2-D image array).

## Components and boundaries

- `ops/scaffold.py`: the φ logic stays inside `scaffold_config`; a small private helper
  `_scan_phi_lines(phi: float) -> list[str]` returns the `[scan.phi]` TOML lines (empty
  list when φ == 0). `WEAK_BEAM_PHI_RAD` is a module constant for reuse/testing.
- `server.py`: thin pass-through; no logic beyond forwarding the two new params.
- `ops/forward.py`: `_render_png` change is self-contained; `run_forward` is untouched.

## Error handling

- Invalid `beam` → `ValueError` naming the allowed values.
- `phi_offset` is trusted as a float (the existing scaffold guards cover structure/material).
- `_render_png` errors propagate as today.

## Testing

**Fast unit (scaffold):**
- Default `scaffold_config()` (no args) emits a `[scan.phi]` block with `value = 0.000175`
  (weak is the default).
- `beam="strong"` emits **no** `[scan.phi]` block (reproduces today's strong output) and
  still `validate_config(...).ok`.
- `phi_offset=<x>` overrides the preset (block carries `<x>`); `phi_offset=0.0` emits no
  block.
- Invalid `beam` (e.g. `"medium"`) raises `ValueError`.
- The default (weak) FCC-simplified config still `validate_config(...).ok`.
- Weak knob works across paths: a non-FCC (BCC) scaffold also carries `[scan.phi]`.

**Fast unit (render):**
- `_render_png(image_2d)` returns non-empty bytes starting with the PNG magic, without
  error, for a representative 2-D array. (Colorbar/axes presence is a manual/visual check.)

**Slow e2e (the behavioral guarantee that would have caught the bug):**
- `run_forward` on a weak scaffold vs a strong scaffold produces **different** images —
  asserted via differing intensity stats (e.g. `vmin`/`vmax`/mean), proving the φ offset
  changes the physics rather than being ignored.

**Regression:** existing `tests/test_ops_scaffold.py` expectations change because the
default output now includes `[scan.phi]`; update those assertions. Existing forward tests
(PNG validity) stay green — `_render_png` still returns a valid PNG.

**Manual:** re-run a default preview in the target client and confirm (a) the contrast is
now weak-beam (dark field, dislocation lit), and (b) pixel axes + colorbar are present.

## Risks

- `1.75e-4 rad` is a single constant, not a per-reflection-correct offset; mitigated by the
  `phi_offset` override and documented as approximate. A rocking-curve-width-derived offset
  is a possible future improvement (tied to the deferred interactive rocking-curve view).
- Changing the default to weak alters `scaffold_config`'s default output — intentional and
  user-directed; covered by updating the scaffold tests.
