# predict_visibility — dislocation visibility ranking — design

Date: 2026-06-18
Status: approved (pending written-spec review)

## Problem

The single most expensive front-of-beamtime decision in DFXM is *which reflection
to use*: a dislocation is **invisible** in the image when the diffraction vector
`g` is perpendicular to its Burgers vector `b` (the g·b = 0 extinction criterion).
A non-expert who has been awarded beamtime — the tool's target user — cannot
easily tell, before burning scarce beam, whether their planned reflection will
even show their defect, or which reachable reflection shows it best. Today the MCP
server can enumerate reachable reflections (`find_reflections`) but says nothing
about *visibility*.

This is the wedge the 2026-06-18 investigation identified as the most defensible
first feature: it lives in the regime where the geometrical-optics model is
**valid** (reachability yes/no, relative g·b magnitude) and emits an **auditable**
artifact (a ranked table / heatmap the expert can check), so the agent *translates*
rather than *judges*. See `memory/future-roadmap-and-product-thesis-2026-06-18.md`.

## Goal

A new tool `predict_visibility` that, for a config's crystal mount + energy, scores
how visible a dislocation will be in each Laue-reachable reflection, using the g·b
criterion, and returns both structured data and a self-contained HTML artifact.

Two modes, one tool (defect-optional):

- **Defect-first** (`burgers` given): reflections **ranked** by g·b for that one
  Burgers vector — "which reflection shows *my* defect best?"
- **Survey/matrix** (`burgers` omitted): a **matrix** of reachable reflections ×
  the structure's slip systems — "I haven't pinned my slip system; show me the
  landscape."

Non-goals (YAGNI for this cut):

- No edge secondary criterion g·(b×u) — surfaced as an honest **caveat** only, not
  computed. (Candidate later enhancement.)
- No "render-to-confirm" (running the forward model per reflection) — that pulls in
  the strong-beam fidelity caveats the model is weakest on.
- No inline MCP-Apps widget — the self-contained `.html` file is client-independent
  and is the deliberate visibility fix; a `ui://` widget can come later.
- No reporting of *unreachable* reflections (reuse `find_reflections`, which yields
  only the reachable set).

## Background: the g·b API in dfxm-geo (verified grounding)

The metric already exists in the library — `predict_visibility` is glue, not new
physics. Exact functions (dfxm-geo v3.0.0, `src/dfxm_geo`):

- `crystal/burgers.py:71` `gb_cos(q_hkl, b_vec) -> float` — `|cos∠(g,b)| ∈ [0,1]`
  (0 = invisible / g⊥b, 1 = max contrast). Normalizes both inputs internally, so it
  accepts an **un-normalized** Cartesian `g` and any non-zero Cartesian `b`.
- `crystal/burgers.py:82` `gb_visible(q_hkl, b_vec, threshold_deg) -> bool` —
  visible ⇔ `gb_cos ≥ cos(90° − threshold_deg)` (e.g. 10° → `gb_cos ≥ ~0.174`).
- `crystal/slip_systems.py:320` `slip_systems(structure, *, families=None)
  -> list[SlipSystem]`. Each `SlipSystem` exposes `.b`, `.n`, `.t`, `.family`
  (all integer-Miller `tuple[int,int,int]`; `.family` a str). Counts: **FCC = 12,
  BCC = 24** (`{110}<111>`=12 + `{112}<111>`=12), **HCP = 30** (5 families).
  `families` narrows the set but accepts **only the library's literal registry
  family strings** (e.g. `"{111}<110>"`, `"{110}<111>"`, `"{112}<111>"`,
  `"{0001}<11-20>"`, …) — friendly names like `"basal"` raise `ValueError` (see
  "Slip-family naming" below).
- `crystal/cell.py` `UnitCell.A` (real-space cell matrix) and `UnitCell.B`
  (reciprocal: cubic `(2π/a)·I`, non-cubic `2π·inv(A)ᵀ`), both 3×3 Cartesian.
- `crystal/oblique.py:17` `CrystalMount` — `.cell` (UnitCell), `.resolved_structure_type`.
- `reciprocal_space/kernel.py` `_crystal_mount_from_toml(crystal_dict | None)` —
  already used by `ops/reflections.py` and `ops/scaffold.py`; returns a default
  FCC cubic mount for `None` (the simplified-FCC config path).

Composition (the whole scoring core):
- `g = mount.cell.B @ [h,k,l]` (Cartesian reciprocal vector; un-normalized is fine).
- Burgers → Cartesian via `b = mount.cell.A @ [u,v,w]` (real-space direction).
- `gb_cos(g, b)` for the value; `gb_visible(g, b, threshold_deg)` for the band.

No private `_q_hkl_unit` dependency is needed (we do not need a *unit* g; `gb_cos`
normalizes). The only non-public import is `_crystal_mount_from_toml`, consistent
with the existing ops layer.

## Architecture — three pieces (chosen approach: thin glue, maximal reuse)

### 1. `ops/visibility.py` — `predict_visibility(...)`

Protocol-agnostic (no fastmcp imports), mirroring `ops/reflections.py`.

```python
def predict_visibility(
    toml_text: str,
    *,
    burgers: tuple[int, int, int] | None = None,
    slip_families: list[str] | None = None,
    hkl_max: int = 3,
    threshold_deg: float = 10.0,
) -> VisibilityResult: ...
```

Flow: parse TOML → `mount = _crystal_mount_from_toml(data.get("crystal"))`,
`keV = reciprocal.keV` (default 17.0); `structure = mount.resolved_structure_type`.
Reachable reflections from the existing `ops.reflections.find_reflections(toml_text,
hkl_max=hkl_max)` (reuses its geometry: θ/η/ω). Then:

- **Defect-first**: `b = mount.cell.A @ burgers`; for each reflection score
  `gb_cos(mount.cell.B @ hkl, b)` + band; **sort by gb_cos desc**.
- **Matrix**: `families = _resolve_families(structure, slip_families)` (alias map,
  below); `systems = slip_systems(structure, families=families)`; for each
  reflection × system score `gb_cos(g, mount.cell.A @ system.b)` + band. The
  per-row `cells[i]` is the gb_cos against `systems[i]` — i.e. `result.systems[i]`
  and `row.cells[i]` share one fixed column order (the deterministic `slip_systems`
  order), the contract every consumer and the heatmap rely on.

Bands: `invisible` if `not gb_visible(...)`; else `strong` vs `weak` split at a
fixed `gb_cos` cut (proposed 0.5) — documented as a display aid, not physics.

The op reads only `mount.cell.A`/`.B`/`.resolved_structure_type` and calls
`find_reflections`/`gb_cos` — **none** of which evaluate `resolved_poisson_ratio`,
so the non-FCC Poisson gate never fires here. An implementer must not add a ν read.

**Slip-family naming.** The library's `families=` accepts only literal registry
strings (`"{0001}<11-20>"`, `"{111}<110>"`, …). To stay usable for non-experts,
`ops/visibility.py` owns a small **friendly→canonical alias map** for HCP
(`basal`→`{0001}<11-20>`, `prismatic`, `pyramidal-a`, `pyramidal-ca-1`,
`pyramidal-ca-2`; FCC/BCC have no common short names, so they take the registry
strings directly). `_resolve_families` resolves each entry as: exact registry name →
pass through; known friendly alias → canonical; otherwise raise a `ValueError` that
lists BOTH the accepted aliases and the structure's registry families. The canonical
strings and the alias map are **validated at import against the live registry** (a
test asserts every alias resolves to a real `slip_systems` family) so a registry
change fails loudly rather than silently mis-mapping. The resolved canonical family
list is echoed in the result (`resolved_families`) for auditability.

### 2. `ops/types.py` — `VisibilityResult`

Two distinct row types (no dual-purpose nullable fields — the reviewer-flagged
incoherence):

```python
@dataclass(frozen=True)
class ReflGeom:               # shared geometry of one reachable reflection
    hkl: tuple[int, int, int]
    theta_deg: float
    eta_deg: float
    omega_deg: float

@dataclass(frozen=True)
class DefectRow:              # defect-first: one reflection scored against one b
    refl: ReflGeom
    gb_cos: float
    visibility: str          # "strong" | "weak" | "invisible"

@dataclass(frozen=True)
class MatrixRow:             # matrix: one reflection scored against every system
    refl: ReflGeom
    cells: list[float]       # gb_cos per slip system; cells[i] ↔ systems[i]

@dataclass(frozen=True)
class SlipSystemLabel:
    plane: tuple[int, int, int]    # from SlipSystem.n
    burgers: tuple[int, int, int]  # from SlipSystem.b
    family: str

@dataclass(frozen=True)
class VisibilityResult:
    mode: str                       # "defect" | "matrix"
    structure: str
    energy_keV: float
    burgers: tuple[int, int, int] | None
    threshold_deg: float
    resolved_families: list[str]    # canonical family strings actually used
    systems: list[SlipSystemLabel]  # matrix columns; [] in defect mode
    defect_rows: list[DefectRow]    # populated in defect mode, [] otherwise
    matrix_rows: list[MatrixRow]    # populated in matrix mode, [] otherwise
    caveats: list[str]
```

`mode` selects which row list is populated; the other is empty. `systems[i]` aligns
with every `MatrixRow.cells[i]`.

### 3. `ui/forward_html.py` — `build_visibility_html(result_dict) -> str`

A pure, self-contained HTML builder beside `build_static_html` /
`build_rocking_html`: a sorted **table** for defect mode (reflection, g·b,
visibility band with a small bar) and a reflections × slip-systems **heatmap** for
matrix mode (cell shade ∝ gb_cos; legend for the invisibility threshold). Same
discipline as the existing builders: inline CSS/JS, **no external origins**,
everything html-escaped, any embedded JSON blob `</`→`<\/` guarded. Caveats render
in a footer panel.

### server.py wiring (thin)

A `@mcp.tool(readOnlyHint=True, idempotentHint=True)` `predict_visibility` mirroring
`find_reflections`: validate `hkl_max ∈ [1,6]` and `0 < threshold_deg < 90`, call
the op, write the HTML through the shared path helper (below), return a structured
dict (`dataclasses.asdict`) plus `html_path`.

## The two bundled bug fixes

### A. `.ui` package missing from the wheel (ship-blocker)

`pyproject.toml:27` `packages = ["dfxm_geo_mcp", "dfxm_geo_mcp.ops",
"dfxm_geo_mcp.knowledge"]` omits `dfxm_geo_mcp.ui`, but `server.py` imports `.ui`.
Editable installs (the test suite) use the source tree so they pass; a **clean
wheel** ships without `ui/` and fails to import the server. Fix: add
`"dfxm_geo_mcp.ui"`. Verify by building a wheel into a fresh venv and importing
`dfxm_geo_mcp.server`.

### B. POSIX `output_path` on Windows → `C:\mnt\...` (silent misplacement)

A leading-`/` path (e.g. the `/mnt/user-data/outputs/...` Cowork convention) is
drive-relative on Windows, so files land under `C:\mnt\...`. Extract a shared
helper and route all three writers through it:

```python
def resolve_output_path(output_path: str | None, *, default: Path, suffix: str) -> Path
```

Behaviour: `None` → `default`. Else, **remap only when running on Windows AND the
path is POSIX-absolute** — precisely: `os.name == "nt"` and `output_path` starts
with `/` and is not a Windows drive path (`not re.match(r"^[A-Za-z]:", output_path)`
and no backslash drive). In that case, put its basename into the cache previews dir
and record that a remap happened. Otherwise use `Path(output_path)` as-is. **On
Linux/macOS a leading `/` is a real absolute path and is NEVER remapped.** Always
enforce `suffix`; return `path` (callers report `path.resolve()`). `run_forward`
(`.png`), `run_rocking` (`.html`), and `predict_visibility` (`.html`) all use it; the
resolved absolute path is always reported. (`predict_visibility` is the third caller
that justifies the extraction; it is **not** a third caller of the analytic-render
core, so that separately-deferred refactor stays untriggered.)

## Error handling

- Unparseable TOML / unbuildable mount → `ValueError` with a clear message
  (wrap `_crystal_mount_from_toml`).
- `burgers` not exactly 3 ints → `ValueError`.
- `hkl_max ∉ [1,6]` or `threshold_deg ∉ (0,90)` → `ValueError` (mirror
  `find_reflections`).
- No reachable reflections at the energy → empty `defect_rows`/`matrix_rows` plus a
  caveat explaining it (no crash).
- `slip_families` entry that is neither a registry name nor a known alias →
  `ValueError` listing both accepted alias names and the structure's registry
  families (see "Slip-family naming").
- Matrix mode on a structure with no registered slip systems → `ValueError` naming
  the structure (points at `register_custom`).
- An arbitrary `burgers` matching no known slip system is still scored (g·b is
  defined for any b) — permissive by design.
- `caveats` ALWAYS includes the edge note: *"g·b = 0 is exact kinematic
  invisibility for screw character; edge dislocations can retain residual contrast
  via the g·(b×u) term not modelled here."* — plus, when families were narrowed, a
  line echoing the resolved canonical families.

## Components and boundaries

- `ops/visibility.py` — pure scoring + assembly; depends only on dfxm-geo + the
  existing `ops.reflections`. Independently testable.
- `ops/types.py` — the result dataclasses (no logic).
- `ui/forward_html.py` — pure HTML rendering; no dfxm-geo, no I/O.
- `server.py` — thin: arg validation, op call, path resolution, file write, dict
  return. The path helper lives in `runtime.py` (or a small `paths.py`) so all three
  tools share it.

## Testing

**Golden physics — scoring core (unit-level, NOT through reachability):**
- FCC `g=(1,1,1)`, `b=[1,-1,0]` → `gb_cos ≈ 0` → `invisible` (textbook invisibility).
- FCC control `g=(2,0,0)`, `b=[1,-1,0]` → `gb_cos` large → `strong`.
- HCP basal ⟨a⟩: `gb_cos(cell.B @ (0,0,2), cell.A @ b) == 0` for each basal Burgers.
  Tested at the scoring-core level on purpose: **(0002) is NOT Laue-reachable at
  17 keV** for the HCP mount, so it never appears in `matrix_rows`/`defect_rows` —
  the full-pipeline test must NOT assert on (0002). (Mirrors the library's
  `test_screw_gb_extinction` physics.)

**Behaviour (full pipeline):**
- Matrix: `len(matrix_rows) == #reachable reflections`; every
  `len(row.cells) == len(systems)`; and **`systems[i]` aligns with `cells[i]`** for a
  hand-checked reflection (alignment, not just shape). For FCC the matrix is
  N×12; for BCC N×24.
- Pick a *reachable* HCP reflection and assert at least one basal-⟨a⟩ cell is
  `invisible` (a reachable analogue of the (0002) golden, so the pipeline path is
  exercised).
- Defect-first `defect_rows` sorted by `gb_cos` descending; deterministic.
- `slip_families` narrowing: HCP `["basal"]` (friendly alias) → only the basal
  column(s); a literal registry string works too; `resolved_families` echoes the
  canonical name; the alias map resolves against the live registry.
- Empty-reachable config → empty row lists + caveat, no exception.
- Arg-validation errors (`hkl_max`, `threshold_deg`, `burgers` length, bad
  `slip_families`).

**HTML builder:**
- Well-formed, self-contained, **no external origins**, html-escaped, `</`→`<\/`
  guarded — same assertions as the existing `forward_html` tests; both modes.

**Path helper:**
- POSIX-absolute `output_path` on Windows remaps into the cache dir and the reported
  path is the resolved absolute path (regression for the wart). Cross-platform-safe
  assertions.

**Gate:** mypy 0, ruff clean, the existing 85 tests stay green; wheel-build import
check for fix A.

## Risks

- **Banding thresholds are presentational.** The strong/weak cut (0.5) and the
  visible/invisible threshold (10°) are display conventions; the caveat must make
  clear g·b is qualitative, not a contrast prediction.
- **Edge dislocations.** g·b alone under-predicts invisibility for edge character;
  the always-on caveat is the mitigation. Promoting g·(b×u) to a real second metric
  is the documented follow-up.
- **Burgers → Cartesian convention.** Must use `cell.A @ b_miller` (real-space) for
  `b` and `cell.B @ hkl` (reciprocal) for `g`; mixing frames silently corrupts the
  dot product. Pinned by the FCC/HCP golden tests.

## Sources

- Investigation outcome: `memory/future-roadmap-and-product-thesis-2026-06-18.md`.
- g·b API grounding: dfxm-geo `crystal/burgers.py`, `crystal/slip_systems.py`,
  `crystal/cell.py`, `crystal/oblique.py`, `reciprocal_space/kernel.py` (v3.0.0).
- Existing tool patterns: `src/dfxm_geo_mcp/ops/reflections.py`,
  `ops/scaffold.py`, `ui/forward_html.py`, `server.py`.
- Known wart record: `memory/session-handoff-2026-06-18.md` (POSIX `output_path`).
