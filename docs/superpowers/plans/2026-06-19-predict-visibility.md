# predict_visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `predict_visibility` MCP tool that scores how visible a dislocation will be in each Laue-reachable reflection (the g·b extinction criterion), returning structured data plus a self-contained HTML artifact, and fix two bundled warts (the `.ui` wheel omission and the POSIX-`output_path`-on-Windows misplacement).

**Architecture:** Thin glue over dfxm-geo, mirroring the existing `find_reflections` flow. A protocol-agnostic op (`ops/visibility.py`) composes the library's `gb_cos` with `find_reflections` + `slip_systems`; result dataclasses live in `ops/types.py`; a pure HTML builder lives beside the existing ones in `ui/forward_html.py`; `server.py` adds a thin tool registration. A shared `runtime.resolve_output_path` helper de-duplicates path resolution across `run_forward`, `run_rocking`, and the new tool.

**Tech Stack:** Python 3.11+, FastMCP 3, dfxm-geo 3.0.0 (local editable install), numpy, pytest/mypy/ruff.

## Global Constraints

- **Python interpreter:** `.venv\Scripts\python.exe` in the repo root. The default `python` is Python 2.7 on this machine — always use the venv. Run all pytest/mypy/ruff through it: `.venv/Scripts/python.exe -m pytest …`.
- **dfxm-geo source of truth** (read-only, for grounding): `C:/Users/borgi/Documents/GM-reworked/Geometrical_Optics_master/src/dfxm_geo` (v3.0.0).
- **Gate (must hold at the end of every task and the whole plan):** `mypy` reports 0 errors on `src/dfxm_geo_mcp/`; `ruff check src tests` is clean; the existing 85 tests stay green. Run `.venv/Scripts/python.exe -m pytest -q -m "not slow"` for the fast gate and `… -m mypy src/dfxm_geo_mcp/` + `… -m ruff check src tests` for the static gates.
- **Self-contained HTML discipline** (the existing `ui/forward_html.py` rule): inline CSS/JS only, **NO external origins** (no `http://`/`https://`), everything passed through `html.escape`, and any embedded JSON blob has `</` replaced with `<\/` to prevent a literal `</script>` break.
- **Frame convention (load-bearing physics):** the reciprocal vector is `g = mount.cell.B @ [h,k,l]`; the Burgers vector is `b = mount.cell.A @ [u,v,w]`. `cell.A` is real-space, `cell.B` is reciprocal. Mixing frames silently corrupts the dot product — pinned by the FCC/HCP golden tests in Task 4.
- **Do NOT read `resolved_poisson_ratio`** anywhere in this feature. Reading it triggers the non-FCC Poisson gate (a `ValueError` for BCC/HCP without a ν source) which must NOT fire here. The op reads only `mount.cell.A`, `mount.cell.B`, `mount.resolved_structure_type`, and calls `find_reflections`/`gb_cos`/`slip_systems` — none of which evaluate ν.
- **Banding constants are presentational, not physics:** `STRONG_CUT = 0.5` (strong vs weak split on `gb_cos`) and the visible/invisible boundary at `threshold_deg` (default 10°). The always-on edge caveat documents this.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml` | add `"dfxm_geo_mcp.ui"` to the wheel `packages` list (fix A) | 1 |
| `src/dfxm_geo_mcp/runtime.py` | new `resolve_output_path` helper (fix B) | 2 |
| `src/dfxm_geo_mcp/server.py` | route `run_forward`/`run_rocking` through the helper (fix B); new `predict_visibility` tool | 2, 7 |
| `src/dfxm_geo_mcp/ops/types.py` | new result dataclasses (`ReflGeom`, `DefectRow`, `MatrixRow`, `SlipSystemLabel`, `VisibilityResult`) | 3 |
| `src/dfxm_geo_mcp/ops/visibility.py` | NEW — pure scoring core + family resolution (Task 4) and `predict_visibility` assembly (Task 5) | 4, 5 |
| `src/dfxm_geo_mcp/ui/forward_html.py` | new `build_visibility_html` builder | 6 |
| `tests/test_runtime_paths.py` | NEW — path-helper unit tests | 2 |
| `tests/test_visibility_types.py` | NEW — dataclass construction/`asdict` | 3 |
| `tests/test_ops_visibility.py` | NEW — scoring-core golden physics, family resolution, full-pipeline behaviour | 4, 5 |
| `tests/test_ui_visibility_html.py` | NEW — HTML builder, both modes | 6 |
| `tests/test_server_visibility.py` | NEW — tool registration + integration through `Client(mcp)` | 7 |

---

## Task 1: Fix A — ship the `.ui` package in the wheel

**Files:**
- Modify: `pyproject.toml:27`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable; a packaging correctness fix.

**Why:** `pyproject.toml:27` lists `packages = ["dfxm_geo_mcp", "dfxm_geo_mcp.ops", "dfxm_geo_mcp.knowledge"]` but `server.py` imports `dfxm_geo_mcp.ui`. Editable installs (the test suite) use the source tree so they pass; a **clean wheel** ships without `ui/` and fails to import the server. `src/dfxm_geo_mcp/ui/__init__.py` already exists, so this is purely the missing list entry.

- [ ] **Step 1: Edit the packages list**

In `pyproject.toml`, change line 27 from:

```toml
packages = ["dfxm_geo_mcp", "dfxm_geo_mcp.ops", "dfxm_geo_mcp.knowledge"]
```

to:

```toml
packages = ["dfxm_geo_mcp", "dfxm_geo_mcp.ops", "dfxm_geo_mcp.ui", "dfxm_geo_mcp.knowledge"]
```

- [ ] **Step 2: Build a wheel and import the server from a fresh venv**

This is the verification — a clean wheel install must import `dfxm_geo_mcp.server` (which imports `.ui`). Run from the repo root:

```bash
.venv/Scripts/python.exe -m pip install build >/dev/null 2>&1 || true
.venv/Scripts/python.exe -m build --wheel
.venv/Scripts/python.exe -m venv /tmp/wheelcheck
/tmp/wheelcheck/Scripts/python.exe -m pip install --quiet "C:/Users/borgi/Documents/GM-reworked/Geometrical_Optics_master[cif]"
/tmp/wheelcheck/Scripts/python.exe -m pip install --quiet --no-deps dist/dfxm_geo_mcp-0.1.0-py3-none-any.whl
/tmp/wheelcheck/Scripts/python.exe -c "import dfxm_geo_mcp.server; import dfxm_geo_mcp.ui.forward_html; print('OK: ui shipped in wheel')"
```

Expected final line: `OK: ui shipped in wheel`. (If `build` is unavailable, the minimum check is `.venv/Scripts/python.exe -m zipfile -l dist/dfxm_geo_mcp-0.1.0-py3-none-any.whl` showing `dfxm_geo_mcp/ui/forward_html.py` in the archive listing.)

- [ ] **Step 3: Confirm the wheel contains the ui module**

Run:

```bash
.venv/Scripts/python.exe -m zipfile -l dist/dfxm_geo_mcp-0.1.0-py3-none-any.whl | grep "dfxm_geo_mcp/ui/"
```

Expected: lines for `dfxm_geo_mcp/ui/__init__.py` and `dfxm_geo_mcp/ui/forward_html.py`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix: ship dfxm_geo_mcp.ui in the wheel (server imports it)"
```

---

## Task 2: Fix B — shared `resolve_output_path` helper + retrofit the two writers

**Files:**
- Modify: `src/dfxm_geo_mcp/runtime.py` (add `resolve_output_path`)
- Modify: `src/dfxm_geo_mcp/server.py` (route `run_forward` and `run_rocking` through it)
- Test: `tests/test_runtime_paths.py` (new)

**Interfaces:**
- Consumes: `runtime.cache_dir()` (existing).
- Produces: `runtime.resolve_output_path(output_path: str | None, *, default: Path, suffix: str) -> Path` — Task 7 calls it with `suffix=".html"`.

**Why:** A leading-`/` path (the Cowork `/mnt/user-data/outputs/...` convention) is drive-relative on Windows, so files silently land under `C:\mnt\...`. The helper remaps **only** that case (POSIX-absolute path on Windows) into the cache previews dir; on Linux/macOS a leading `/` is a real absolute path and is NEVER remapped.

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_runtime_paths.py`:

```python
"""resolve_output_path: enforce a suffix, and remap the Cowork POSIX-absolute
path ONLY when running on Windows (where a leading-/ path is drive-relative)."""

from __future__ import annotations

import os
from pathlib import Path

from dfxm_geo_mcp import runtime


def test_none_returns_default():
    default = Path("/tmp/d.html")
    assert runtime.resolve_output_path(None, default=default, suffix=".html") == default


def test_suffix_enforced_when_missing(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    out = runtime.resolve_output_path("/tmp/x.txt", default=Path("/tmp/d.html"), suffix=".html")
    assert out.name == "x.html"


def test_posix_absolute_on_windows_is_remapped(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    out = runtime.resolve_output_path(
        "/mnt/user-data/outputs/vis.html", default=tmp_path / "d.html", suffix=".html"
    )
    assert out.parent == tmp_path / "previews"
    assert out.name == "vis.html"


def test_windows_drive_path_passthrough(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    out = runtime.resolve_output_path("C:/proj/out.html", default=Path("d.html"), suffix=".html")
    assert "previews" not in str(out)
    assert out.name == "out.html"


def test_posix_leading_slash_not_remapped_on_posix(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    out = runtime.resolve_output_path(
        "/mnt/user-data/outputs/vis.html", default=tmp_path / "d.html", suffix=".html"
    )
    assert "previews" not in str(out)
    assert out.name == "vis.html"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_paths.py -q`
Expected: FAIL — `AttributeError: module 'dfxm_geo_mcp.runtime' has no attribute 'resolve_output_path'`.

- [ ] **Step 3: Implement the helper**

In `src/dfxm_geo_mcp/runtime.py`, add `import re` to the imports at the top (next to `import os`), then add this function (after `cache_dir`):

```python
def resolve_output_path(output_path: str | None, *, default: Path, suffix: str) -> Path:
    """Resolve a user output path to a concrete file, enforcing ``suffix``.

    ``None`` -> ``default``. A POSIX-absolute path on Windows (leading ``/``, not a
    drive path) is the Cowork ``/mnt/...`` convention, which Windows reads as
    drive-relative (``C:\\mnt\\...``) and silently misplaces; remap it into the
    cache previews dir by basename. On POSIX a leading ``/`` is a real absolute
    path and is NEVER remapped. ``suffix`` (e.g. ``".png"``, ``".html"``) is
    always enforced. Callers report ``path.resolve()``.
    """
    if output_path is None:
        path = default
    elif (
        os.name == "nt"
        and output_path.startswith("/")
        and re.match(r"^[A-Za-z]:", output_path) is None
        and "\\" not in output_path
    ):
        path = cache_dir() / "previews" / Path(output_path).name
    else:
        path = Path(output_path)
    if path.suffix.lower() != suffix:
        path = path.with_suffix(suffix)
    return path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_paths.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Retrofit `run_forward` in `server.py`**

In `src/dfxm_geo_mcp/server.py`, replace the `output_path` resolution block in `run_forward` (currently lines ~138-144):

```python
    if output_path is not None:
        path = Path(output_path)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
    else:
        path = runtime.cache_dir() / "previews" / "forward_preview.png"
    path.parent.mkdir(parents=True, exist_ok=True)
```

with:

```python
    path = runtime.resolve_output_path(
        output_path,
        default=runtime.cache_dir() / "previews" / "forward_preview.png",
        suffix=".png",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Retrofit `run_rocking` in `server.py`**

In `run_rocking`, replace its block (currently lines ~200-206):

```python
    if output_path is not None:
        path = Path(output_path)
        if path.suffix.lower() != ".html":
            path = path.with_suffix(".html")
    else:
        path = runtime.cache_dir() / "previews" / "forward_rocking.html"
    path.parent.mkdir(parents=True, exist_ok=True)
```

with:

```python
    path = runtime.resolve_output_path(
        output_path,
        default=runtime.cache_dir() / "previews" / "forward_rocking.html",
        suffix=".html",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
```

**Then remove the now-unused import.** `Path` was used ONLY in the two blocks just replaced (lines 139 and 201 — no other use in `server.py`, and Task 7's new tool uses `runtime.resolve_output_path` not `Path`). Leaving the import would fail the ruff gate with `F401 pathlib.Path imported but unused`. Delete line 6 of `src/dfxm_geo_mcp/server.py`:

```python
from pathlib import Path
```

- [ ] **Step 7: Run the existing output-path/rocking tests to confirm no regression**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_forward_output_path.py tests/test_server_rocking.py tests/test_runtime_paths.py -q`
Expected: PASS (the existing tests pass real absolute tmp paths → the else branch → suffix enforced; behaviour is unchanged).

- [ ] **Step 8: Static gates + commit**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` (expect 0 errors) and `.venv/Scripts/python.exe -m ruff check src tests` (expect clean).

```bash
git add src/dfxm_geo_mcp/runtime.py src/dfxm_geo_mcp/server.py tests/test_runtime_paths.py
git commit -m "fix: shared resolve_output_path helper; remap POSIX-absolute output_path on Windows"
```

---

## Task 3: Result dataclasses in `ops/types.py`

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/types.py` (append the new dataclasses)
- Test: `tests/test_visibility_types.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces (Tasks 5, 6, 7 rely on these exact names/types):
  - `ReflGeom(hkl: tuple[int,int,int], theta_deg: float, eta_deg: float, omega_deg: float)`
  - `DefectRow(refl: ReflGeom, gb_cos: float, visibility: str)`
  - `MatrixRow(refl: ReflGeom, cells: list[float])`
  - `SlipSystemLabel(plane: tuple[int,int,int], burgers: tuple[int,int,int], family: str)`
  - `VisibilityResult(mode, structure, energy_keV, burgers, threshold_deg, resolved_families, systems, defect_rows, matrix_rows, caveats)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_visibility_types.py`:

```python
import dataclasses

from dfxm_geo_mcp.ops.types import (
    DefectRow,
    MatrixRow,
    ReflGeom,
    SlipSystemLabel,
    VisibilityResult,
)


def test_dataclasses_construct_and_asdict_round_trips():
    geom = ReflGeom(hkl=(1, 1, 1), theta_deg=8.0, eta_deg=0.0, omega_deg=8.0)
    res = VisibilityResult(
        mode="defect",
        structure="fcc",
        energy_keV=17.0,
        burgers=(1, -1, 0),
        threshold_deg=10.0,
        resolved_families=[],
        systems=[SlipSystemLabel(plane=(1, 1, 1), burgers=(1, -1, 0), family="{111}<110>")],
        defect_rows=[DefectRow(refl=geom, gb_cos=0.0, visibility="invisible")],
        matrix_rows=[MatrixRow(refl=geom, cells=[0.0, 0.7])],
        caveats=["edge note"],
    )
    d = dataclasses.asdict(res)
    assert d["mode"] == "defect"
    assert d["defect_rows"][0]["visibility"] == "invisible"
    assert d["defect_rows"][0]["refl"]["hkl"] == (1, 1, 1)
    assert d["matrix_rows"][0]["cells"] == [0.0, 0.7]
    assert d["systems"][0]["family"] == "{111}<110>"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_visibility_types.py -q`
Expected: FAIL — `ImportError: cannot import name 'DefectRow'`.

- [ ] **Step 3: Implement the dataclasses**

Append to `src/dfxm_geo_mcp/ops/types.py` (the file already has `from dataclasses import dataclass` and `from __future__ import annotations`):

```python
@dataclass(frozen=True)
class ReflGeom:
    """Shared geometry of one Laue-reachable reflection (angles in degrees)."""

    hkl: tuple[int, int, int]
    theta_deg: float
    eta_deg: float
    omega_deg: float


@dataclass(frozen=True)
class DefectRow:
    """Defect-first: one reflection scored against a single Burgers vector."""

    refl: ReflGeom
    gb_cos: float
    visibility: str  # "strong" | "weak" | "invisible"


@dataclass(frozen=True)
class MatrixRow:
    """Matrix: one reflection scored against every slip system.

    ``cells[i]`` is the gb_cos against ``VisibilityResult.systems[i]`` — the two
    share one fixed column order (the deterministic ``slip_systems`` order). This
    alignment is the contract every consumer and the heatmap rely on.
    """

    refl: ReflGeom
    cells: list[float]


@dataclass(frozen=True)
class SlipSystemLabel:
    """A matrix column label, sourced from a dfxm-geo ``SlipSystem``."""

    plane: tuple[int, int, int]    # SlipSystem.n
    burgers: tuple[int, int, int]  # SlipSystem.b
    family: str


@dataclass(frozen=True)
class VisibilityResult:
    """predict_visibility output. ``mode`` selects which row list is populated;
    the other is empty. ``systems[i]`` aligns with every ``MatrixRow.cells[i]``."""

    mode: str                        # "defect" | "matrix"
    structure: str
    energy_keV: float
    burgers: tuple[int, ...] | None  # the user's Burgers vector in defect mode
    threshold_deg: float
    resolved_families: list[str]     # canonical family strings actually used
    systems: list[SlipSystemLabel]   # matrix columns; [] in defect mode
    defect_rows: list[DefectRow]     # populated in defect mode, [] otherwise
    matrix_rows: list[MatrixRow]     # populated in matrix mode, [] otherwise
    caveats: list[str]
```

Note: `VisibilityResult.burgers` is typed `tuple[int, ...] | None` (not `tuple[int,int,int]`) so the op can assign `tuple(int(x) for x in burgers)` — a variable-length tuple — without a mypy error; the exact-3 length is enforced at runtime in Task 5.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_visibility_types.py -q`
Expected: PASS.

- [ ] **Step 5: Static gates + commit**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` (0 errors) and `.venv/Scripts/python.exe -m ruff check src tests` (clean).

```bash
git add src/dfxm_geo_mcp/ops/types.py tests/test_visibility_types.py
git commit -m "feat: visibility result dataclasses (ReflGeom/DefectRow/MatrixRow/SlipSystemLabel/VisibilityResult)"
```

---

## Task 4: Scoring core + slip-family resolution (`ops/visibility.py`)

**Files:**
- Create: `src/dfxm_geo_mcp/ops/visibility.py`
- Test: `tests/test_ops_visibility.py` (new — golden physics + family-resolution sections)

**Interfaces:**
- Consumes: dfxm-geo `crystal.burgers.gb_cos`, `crystal.slip_systems.slip_systems`, `reciprocal_space.kernel._crystal_mount_from_toml`.
- Produces (Task 5 relies on these):
  - `EDGE_CAVEAT: str` — the always-on edge note.
  - `STRONG_CUT: float = 0.5`
  - `_band(gb_cos: float, threshold_deg: float) -> str` — `"invisible" | "weak" | "strong"`
  - `_score(mount, hkl: tuple[int,int,int], b_miller: tuple[int, ...], threshold_deg: float) -> tuple[float, str]` — applies the A/B frame convention; returns `(gb_cos, band)`.
  - `_HCP_ALIASES: dict[str, str]` — friendly→canonical.
  - `_resolve_families(structure: str, slip_families: list[str] | None) -> list[str] | None`

**Why this is its own task:** the frame convention and banding are the load-bearing physics. This task pins them with unit-level golden tests (NOT through reachability), exactly as the spec's `test_screw_gb_extinction` does upstream, before any assembly is built on top.

- [ ] **Step 1: Write the failing scoring-core + family tests**

Create `tests/test_ops_visibility.py`:

```python
"""predict_visibility scoring core + slip-family resolution."""

from __future__ import annotations

import tomllib

import pytest

from dfxm_geo.crystal.slip_systems import slip_systems
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops import visibility as vis

HCP_TOML = (
    "[crystal]\n"
    'lattice = "hexagonal"\n'
    "a = 2.951e-10\nc = 4.684e-10\n"
    'structure_type = "hcp"\n'
    'material = "Ti"\n'
    "mount_x = [2, -1, 0]\n"
    "mount_y = [0,  1, 0]\n"
    "mount_z = [0,  0, 1]\n"
)


def _fcc_mount():
    return _crystal_mount_from_toml(None)


def _hcp_mount():
    return _crystal_mount_from_toml(tomllib.loads(HCP_TOML)["crystal"])


def test_fcc_screw_invisibility_golden():
    # Textbook g.b = 0: g=(1,1,1) perpendicular to b=[1,-1,0].
    gbcos, band = vis._score(_fcc_mount(), (1, 1, 1), (1, -1, 0), 10.0)
    assert gbcos == pytest.approx(0.0, abs=1e-9)
    assert band == "invisible"


def test_fcc_strong_control_golden():
    gbcos, band = vis._score(_fcc_mount(), (2, 0, 0), (1, -1, 0), 10.0)
    assert gbcos == pytest.approx(0.70710678, abs=1e-6)
    assert band == "strong"


def test_hcp_basal_a_invisible_against_0002_golden():
    # Scoring-core level on purpose: (0002) is NOT Laue-reachable at 17 keV for
    # the HCP mount, so it never appears in matrix_rows/defect_rows. Mirrors the
    # library's test_screw_gb_extinction.
    mount = _hcp_mount()
    for s in slip_systems("hcp", families=["{0001}<11-20>"]):
        gbcos, band = vis._score(mount, (0, 0, 2), s.b, 10.0)
        assert gbcos == pytest.approx(0.0, abs=1e-9)
        assert band == "invisible"


def test_band_matches_gb_visible_threshold():
    # The 10-degree boundary: cos(90-10) = cos(80) ~ 0.17365.
    assert vis._band(0.18, 10.0) == "weak"
    assert vis._band(0.17, 10.0) == "invisible"
    assert vis._band(0.6, 10.0) == "strong"
    assert vis._band(0.5, 10.0) == "strong"   # STRONG_CUT is inclusive
    assert vis._band(0.49, 10.0) == "weak"


def test_resolve_families_alias_and_passthrough():
    # friendly alias resolves to canonical
    assert vis._resolve_families("hcp", ["basal"]) == ["{0001}<11-20>"]
    # a literal registry string passes through unchanged
    assert vis._resolve_families("hcp", ["{10-10}<11-20>"]) == ["{10-10}<11-20>"]
    # None -> None (no narrowing)
    assert vis._resolve_families("fcc", None) is None
    # FCC takes its registry string directly
    assert vis._resolve_families("fcc", ["{111}<110>"]) == ["{111}<110>"]


def test_resolve_families_unknown_raises_listing_both():
    with pytest.raises(ValueError) as exc:
        vis._resolve_families("hcp", ["bogus"])
    msg = str(exc.value)
    assert "basal" in msg                # accepted aliases listed
    assert "{0001}<11-20>" in msg        # registry families listed


def test_resolve_families_alias_for_wrong_structure_raises():
    # "basal" is an HCP-only alias; on FCC it must raise (canonical not in registry)
    with pytest.raises(ValueError):
        vis._resolve_families("fcc", ["basal"])


def test_alias_map_validates_against_live_registry():
    # Every alias canonical must be a real hcp family (guard against registry drift).
    hcp_families = {s.family for s in slip_systems("hcp")}
    for canonical in vis._HCP_ALIASES.values():
        assert canonical in hcp_families
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_visibility.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dfxm_geo_mcp.ops.visibility'`.

- [ ] **Step 3: Implement the scoring core + family resolution**

Create `src/dfxm_geo_mcp/ops/visibility.py`:

```python
"""predict_visibility: score dislocation visibility (g.b) across reachable reflections.

Thin glue over dfxm-geo — no new physics. The scoring core composes the
library's ``gb_cos`` with the A/B frame convention; the assembly (Task 5) reuses
``ops.reflections.find_reflections`` for the reachable set and
``crystal.slip_systems.slip_systems`` for the matrix columns.
"""

from __future__ import annotations

import numpy as np

from dfxm_geo.crystal.burgers import gb_cos
from dfxm_geo.crystal.slip_systems import slip_systems

# Strong vs weak split on gb_cos (presentational, NOT a contrast prediction).
STRONG_CUT = 0.5

# Always-on caveat: g.b alone under-predicts edge-dislocation visibility.
EDGE_CAVEAT = (
    "g.b = 0 is exact kinematic invisibility for screw character; edge "
    "dislocations can retain residual contrast via the g.(b x u) term not "
    "modelled here."
)

# Friendly -> canonical registry family names for HCP (the library's families=
# accepts only the literal registry strings). FCC/BCC have no common short names,
# so callers pass the registry strings directly. Validated against the live
# registry at import (see _validate_aliases below).
_HCP_ALIASES: dict[str, str] = {
    "basal": "{0001}<11-20>",
    "prismatic": "{10-10}<11-20>",
    "pyramidal-a": "{10-11}<11-20>",
    "pyramidal-ca-1": "{10-11}<11-23>",
    "pyramidal-ca-2": "{11-22}<11-23>",
}


def _validate_aliases() -> None:
    """Fail loudly at import if an alias canonical is no longer a real hcp family."""
    families = {s.family for s in slip_systems("hcp")}
    for friendly, canonical in _HCP_ALIASES.items():
        if canonical not in families:
            raise AssertionError(
                f"slip-family alias {friendly!r} -> {canonical!r} is not in the "
                f"live hcp registry {sorted(families)}"
            )


_validate_aliases()


def _band(gb_cos_value: float, threshold_deg: float) -> str:
    """Classify a gb_cos value into 'invisible' | 'weak' | 'strong'.

    Mirrors the library's ``gb_visible``: invisible when gb_cos is below
    cos(90 - threshold_deg); otherwise strong at/above STRONG_CUT, else weak.
    """
    visible_cut = float(np.cos(np.deg2rad(90.0 - threshold_deg)))
    if gb_cos_value < visible_cut:
        return "invisible"
    return "strong" if gb_cos_value >= STRONG_CUT else "weak"


def _score(
    mount: object,
    hkl: tuple[int, int, int],
    b_miller: tuple[int, ...],
    threshold_deg: float,
) -> tuple[float, str]:
    """Score one reflection against one Burgers vector. Returns (gb_cos, band).

    Frame convention (load-bearing): g = cell.B @ hkl (reciprocal), b = cell.A @
    b_miller (real-space). gb_cos normalizes both internally, so an un-normalized
    g and any non-zero b are fine.
    """
    g = mount.cell.B @ np.asarray(hkl, dtype=float)            # type: ignore[attr-defined]
    b = mount.cell.A @ np.asarray(b_miller, dtype=float)       # type: ignore[attr-defined]
    value = gb_cos(g, b)
    return value, _band(value, threshold_deg)


def _resolve_families(structure: str, slip_families: list[str] | None) -> list[str] | None:
    """Map each requested family to a canonical registry string for ``structure``.

    Resolution per entry: exact registry name -> pass through; known friendly
    alias whose canonical is in this structure's registry -> canonical; otherwise
    raise a ValueError listing BOTH the accepted aliases and the structure's
    registry families. ``None`` (no narrowing) returns ``None``.
    """
    if slip_families is None:
        return None
    registry = {s.family for s in slip_systems(structure)}
    resolved: list[str] = []
    for fam in slip_families:
        if fam in registry:
            resolved.append(fam)
        elif fam in _HCP_ALIASES and _HCP_ALIASES[fam] in registry:
            resolved.append(_HCP_ALIASES[fam])
        else:
            raise ValueError(
                f"unknown slip family {fam!r} for structure {structure!r}. "
                f"Accepted aliases: {sorted(_HCP_ALIASES)}. "
                f"Registry families: {sorted(registry)}."
            )
    return resolved
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_visibility.py -q`
Expected: PASS (all scoring-core + family-resolution tests).

- [ ] **Step 5: Static gates + commit**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` (0 errors) and `.venv/Scripts/python.exe -m ruff check src tests` (clean).

```bash
git add src/dfxm_geo_mcp/ops/visibility.py tests/test_ops_visibility.py
git commit -m "feat: visibility scoring core (g.b frame convention + banding) and slip-family resolution"
```

---

## Task 5: `predict_visibility` op assembly (defect + matrix flow)

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/visibility.py` (add `predict_visibility`)
- Test: `tests/test_ops_visibility.py` (append the full-pipeline behaviour section)

**Interfaces:**
- Consumes: Task 3 dataclasses, Task 4 helpers (`_score`, `_resolve_families`, `EDGE_CAVEAT`), `ops.reflections.find_reflections`, dfxm-geo `_crystal_mount_from_toml`, `slip_systems`.
- Produces (Task 7 relies on this):
  - `predict_visibility(toml_text: str, *, burgers: tuple[int, ...] | None = None, slip_families: list[str] | None = None, hkl_max: int = 3, threshold_deg: float = 10.0) -> VisibilityResult`

- [ ] **Step 1: Write the failing full-pipeline tests**

Append to `tests/test_ops_visibility.py`:

```python
from dfxm_geo_mcp.ops.types import VisibilityResult


def test_defect_mode_rows_sorted_descending_and_deterministic():
    res = vis.predict_visibility("", burgers=(1, -1, 0), hkl_max=2)
    assert isinstance(res, VisibilityResult)
    assert res.mode == "defect"
    assert res.structure == "fcc"
    assert res.matrix_rows == [] and res.systems == []
    assert len(res.defect_rows) > 0
    cosines = [r.gb_cos for r in res.defect_rows]
    assert cosines == sorted(cosines, reverse=True)
    # determinism
    res2 = vis.predict_visibility("", burgers=(1, -1, 0), hkl_max=2)
    assert [r.refl.hkl for r in res2.defect_rows] == [r.refl.hkl for r in res.defect_rows]
    # always-on edge caveat present
    assert any("g.(b x u)" in c for c in res.caveats)


def test_matrix_mode_shape_and_column_alignment():
    res = vis.predict_visibility("", hkl_max=2)  # FCC, no burgers -> matrix
    assert res.mode == "matrix"
    assert res.defect_rows == [] and res.burgers is None
    assert len(res.systems) == 12  # FCC {111}<110>
    assert len(res.matrix_rows) == len(vis.find_reflections("", hkl_max=2))
    for row in res.matrix_rows:
        assert len(row.cells) == len(res.systems)
    # alignment (not just shape): recompute one cell independently
    from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml
    mount = _crystal_mount_from_toml(None)
    row = res.matrix_rows[0]
    i = 0
    expected, _ = vis._score(mount, row.refl.hkl, res.systems[i].burgers, res.threshold_deg)
    assert row.cells[i] == pytest.approx(expected, abs=1e-12)


def test_matrix_mode_bcc_has_24_columns():
    toml = (
        "[reciprocal]\nhkl = [1, 1, 0]\nkeV = 17.0\nbackend = \"analytic\"\nbeamstop = false\n"
        "[crystal]\n"
        'lattice = "cubic"\na = 2.87e-10\n'
        'structure_type = "bcc"\n'
        'material = "Fe"\n'
        "mount_x = [1, 1, 0]\nmount_y = [-1, 1, 0]\nmount_z = [0, 0, 1]\n"
        "[geometry]\n"
        'mode = "oblique"\n'
        # eta is cross-checked by the validator, but predict_visibility never runs
        # the validator; find_reflections only needs the mount + energy.
    )
    res = vis.predict_visibility(toml, hkl_max=2)
    assert res.structure == "bcc"
    assert len(res.systems) == 24


def test_matrix_mode_hcp_has_reachable_basal_invisible_cell():
    res = vis.predict_visibility(HCP_TOML, hkl_max=2)
    assert res.structure == "hcp"
    basal_cols = [i for i, s in enumerate(res.systems) if s.family == "{0001}<11-20>"]
    assert basal_cols
    invisible_cut = float(__import__("numpy").cos(__import__("numpy").deg2rad(80.0)))
    found = any(
        row.cells[i] < invisible_cut for row in res.matrix_rows for i in basal_cols
    )
    assert found, "expected at least one reachable HCP basal-<a> cell to be invisible"


def test_matrix_mode_family_narrowing_with_alias():
    res = vis.predict_visibility(HCP_TOML, slip_families=["basal"], hkl_max=2)
    assert res.resolved_families == ["{0001}<11-20>"]
    assert all(s.family == "{0001}<11-20>" for s in res.systems)
    # narrowing echoes a caveat naming the canonical family
    assert any("{0001}<11-20>" in c for c in res.caveats)


def test_empty_reachable_returns_empty_rows_with_caveat(monkeypatch):
    monkeypatch.setattr(vis, "find_reflections", lambda toml_text, hkl_max=3: [])
    res = vis.predict_visibility("", burgers=(1, -1, 0))
    assert res.defect_rows == []
    assert any("reachable" in c.lower() for c in res.caveats)


def test_burgers_wrong_length_raises():
    with pytest.raises(ValueError):
        vis.predict_visibility("", burgers=(1, 0))  # only 2 ints


def test_arg_range_validation():
    with pytest.raises(ValueError):
        vis.predict_visibility("", hkl_max=0)
    with pytest.raises(ValueError):
        vis.predict_visibility("", threshold_deg=0.0)
    with pytest.raises(ValueError):
        vis.predict_visibility("", threshold_deg=90.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_visibility.py -q`
Expected: FAIL — `AttributeError: module 'dfxm_geo_mcp.ops.visibility' has no attribute 'predict_visibility'`.

- [ ] **Step 3: Implement `predict_visibility`**

Add to the top of `src/dfxm_geo_mcp/ops/visibility.py`, in the imports block:

```python
import tomllib

from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops.reflections import find_reflections
from dfxm_geo_mcp.ops.types import (
    DefectRow,
    MatrixRow,
    ReflGeom,
    SlipSystemLabel,
    VisibilityResult,
)
```

Then append this function to the module:

```python
def predict_visibility(
    toml_text: str,
    *,
    burgers: tuple[int, ...] | None = None,
    slip_families: list[str] | None = None,
    hkl_max: int = 3,
    threshold_deg: float = 10.0,
) -> VisibilityResult:
    """Score dislocation visibility (g.b) across the config's reachable reflections.

    Two modes: defect-first (``burgers`` given) ranks reflections by gb_cos for
    that one Burgers vector; survey/matrix (``burgers`` omitted) scores every
    reachable reflection against every slip system of the resolved structure.
    """
    if not 1 <= hkl_max <= 6:
        raise ValueError(f"hkl_max must be between 1 and 6 (got {hkl_max})")
    if not 0.0 < threshold_deg < 90.0:
        raise ValueError(f"threshold_deg must be in (0, 90) (got {threshold_deg})")

    data = tomllib.loads(toml_text) if toml_text.strip() else {}
    try:
        mount = _crystal_mount_from_toml(data.get("crystal"))
    except Exception as exc:  # unparseable / unbuildable mount
        raise ValueError(f"could not build a crystal mount from the config: {exc}") from exc
    keV = float(data.get("reciprocal", {}).get("keV", 17.0))
    structure = mount.resolved_structure_type

    refls = find_reflections(toml_text, hkl_max=hkl_max)
    caveats = [EDGE_CAVEAT]
    if not refls:
        caveats.append(
            "No Laue-reachable reflections at this energy/mount up to "
            f"hkl_max={hkl_max}; nothing to score."
        )

    def _geom(r: object) -> ReflGeom:
        return ReflGeom(
            hkl=r.hkl, theta_deg=r.theta_deg, eta_deg=r.eta_deg, omega_deg=r.omega_deg  # type: ignore[attr-defined]
        )

    if burgers is not None:
        b = tuple(int(x) for x in burgers)
        if len(b) != 3:
            raise ValueError(f"burgers must have exactly 3 Miller indices, got {len(b)}: {b}")
        defect_rows: list[DefectRow] = []
        for r in refls:
            value, band = _score(mount, r.hkl, b, threshold_deg)
            defect_rows.append(DefectRow(refl=_geom(r), gb_cos=value, visibility=band))
        defect_rows.sort(key=lambda d: d.gb_cos, reverse=True)
        return VisibilityResult(
            mode="defect",
            structure=structure,
            energy_keV=keV,
            burgers=b,
            threshold_deg=threshold_deg,
            resolved_families=[],
            systems=[],
            defect_rows=defect_rows,
            matrix_rows=[],
            caveats=caveats,
        )

    resolved = _resolve_families(structure, slip_families)
    try:
        systems = slip_systems(structure, families=resolved)
    except ValueError as exc:
        raise ValueError(
            f"structure {structure!r} has no registered slip systems; register one "
            f"with dfxm_geo.crystal.slip_systems.register_custom. ({exc})"
        ) from exc
    if not systems:
        raise ValueError(f"no slip systems for structure {structure!r} with families={resolved!r}")

    labels = [SlipSystemLabel(plane=s.n, burgers=s.b, family=s.family) for s in systems]
    matrix_rows: list[MatrixRow] = []
    for r in refls:
        cells = [_score(mount, r.hkl, s.b, threshold_deg)[0] for s in systems]
        matrix_rows.append(MatrixRow(refl=_geom(r), cells=cells))

    resolved_families = (
        resolved if resolved is not None else list(dict.fromkeys(s.family for s in systems))
    )
    if resolved is not None:
        caveats.append("Slip families narrowed to: " + ", ".join(resolved) + ".")

    return VisibilityResult(
        mode="matrix",
        structure=structure,
        energy_keV=keV,
        burgers=None,
        threshold_deg=threshold_deg,
        resolved_families=resolved_families,
        systems=labels,
        defect_rows=[],
        matrix_rows=matrix_rows,
        caveats=caveats,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ops_visibility.py -q`
Expected: PASS (scoring core + full-pipeline behaviour).

- [ ] **Step 5: Static gates + commit**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` (0 errors) and `.venv/Scripts/python.exe -m ruff check src tests` (clean).

```bash
git add src/dfxm_geo_mcp/ops/visibility.py tests/test_ops_visibility.py
git commit -m "feat: predict_visibility op (defect-first ranking + reflection x slip-system matrix)"
```

---

## Task 6: `build_visibility_html` — self-contained HTML artifact

**Files:**
- Modify: `src/dfxm_geo_mcp/ui/forward_html.py` (add `build_visibility_html`)
- Test: `tests/test_ui_visibility_html.py` (new)

**Interfaces:**
- Consumes: a plain dict (the shape of `dataclasses.asdict(VisibilityResult)` from Task 5).
- Produces (Task 7 relies on this): `build_visibility_html(result: dict[str, Any]) -> str`

**Why a dict, not the dataclass:** the builder stays pure (no dfxm-geo, no dataclass import) and the server already produces the dict via `dataclasses.asdict`, exactly like the other builders take primitives.

- [ ] **Step 1: Write the failing builder tests**

Create `tests/test_ui_visibility_html.py`:

```python
import json

from dfxm_geo_mcp.ui.forward_html import build_visibility_html

_DEFECT = {
    "mode": "defect",
    "structure": "fcc",
    "energy_keV": 17.0,
    "burgers": [1, -1, 0],
    "threshold_deg": 10.0,
    "resolved_families": [],
    "systems": [],
    "defect_rows": [
        {"refl": {"hkl": [2, 0, 0], "theta_deg": 8.0, "eta_deg": 0.0, "omega_deg": 8.0},
         "gb_cos": 0.707, "visibility": "strong"},
        {"refl": {"hkl": [1, 1, 1], "theta_deg": 7.0, "eta_deg": 0.0, "omega_deg": 7.0},
         "gb_cos": 0.0, "visibility": "invisible"},
    ],
    "matrix_rows": [],
    "caveats": ["g.b = 0 is exact kinematic invisibility for screw character; ..."],
}

_MATRIX = {
    "mode": "matrix",
    "structure": "fcc",
    "energy_keV": 17.0,
    "burgers": None,
    "threshold_deg": 10.0,
    "resolved_families": ["{111}<110>"],
    "systems": [
        {"plane": [1, 1, 1], "burgers": [1, -1, 0], "family": "{111}<110>"},
        {"plane": [1, 1, 1], "burgers": [-1, 0, 1], "family": "{111}<110>"},
    ],
    "defect_rows": [],
    "matrix_rows": [
        {"refl": {"hkl": [2, 0, 0], "theta_deg": 8.0, "eta_deg": 0.0, "omega_deg": 8.0},
         "cells": [0.707, 0.0]},
    ],
    "caveats": ["edge note"],
}


def _assert_self_contained(html: str):
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    # embedded JSON blob is </ guarded
    assert "</script" not in html.replace("</script>", "")  # no stray close before the real ones


def test_defect_html_renders_table_and_is_self_contained():
    html = build_visibility_html(_DEFECT)
    _assert_self_contained(html)
    assert "strong" in html and "invisible" in html
    assert "2, 0, 0" in html or "[2, 0, 0]" in html  # reflection rendered
    assert "g.b" in html  # caveat surfaced (escaped text)


def test_matrix_html_renders_heatmap_and_columns():
    html = build_visibility_html(_MATRIX)
    _assert_self_contained(html)
    assert "{111}&lt;110&gt;" in html  # family label, html-escaped
    # both system columns present
    assert html.count("1, -1, 0") >= 1


def test_embedded_blob_round_trips_and_is_guarded():
    html = build_visibility_html(_MATRIX)
    start = html.index('id="dfxm-vis"')
    blob = html[html.index(">", start) + 1 : html.index("</script>", start)]
    data = json.loads(blob)
    assert data["mode"] == "matrix"
    # the raw json.dumps would contain </ only if a value did; the guard replaces it
    assert "<\\/" in html or "</" not in json.dumps(_MATRIX)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_visibility_html.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_visibility_html'`.

- [ ] **Step 3: Implement the builder**

Append to `src/dfxm_geo_mcp/ui/forward_html.py` (the module already imports `html as _htmllib`, `json`, and `Any`):

```python
_VIS_CSS = """
  .vis table{border-collapse:collapse;font-size:13px;margin-top:8px}
  .vis th,.vis td{padding:4px 8px;text-align:left;white-space:nowrap}
  .vis th{color:#8a90a0;font-weight:600;border-bottom:1px solid #2a2a35}
  .vis td{color:#cdd2da;font-variant-numeric:tabular-nums}
  .bar{display:inline-block;height:9px;border-radius:3px;background:#e0457b;vertical-align:middle}
  .b-strong{color:#7fe0a0}.b-weak{color:#e0c34a}.b-invisible{color:#e0457b}
  .heat{overflow:auto;max-width:100%}
  .heat td.cell{text-align:center;color:#0b0b0f;font-weight:600;border:1px solid #1a1a22}
  .foot{margin-top:18px;padding:12px 14px;background:#15151c;border-radius:8px;color:#9aa1ad;font-size:12px}
  .foot li{margin:3px 0}
  .legend{margin:6px 0;color:#8a90a0;font-size:12px}
"""


def _vis_caption(result: dict[str, Any]) -> str:
    bits = [
        f"structure {result.get('structure')}",
        f"{result.get('energy_keV')} keV",
        f"threshold {result.get('threshold_deg')} deg",
    ]
    if result.get("mode") == "defect" and result.get("burgers") is not None:
        bits.insert(0, "Burgers " + ", ".join(str(v) for v in result["burgers"]))
    return _htmllib.escape(" - ".join(bits))


def _hkl_str(hkl: Any) -> str:
    return ", ".join(str(v) for v in hkl)


def _defect_body(result: dict[str, Any]) -> str:
    rows = []
    for r in result.get("defect_rows", []):
        gbcos = float(r["gb_cos"])
        band = str(r["visibility"])
        width = max(1, round(gbcos * 120))
        rows.append(
            "<tr>"
            f"<td>{_htmllib.escape(_hkl_str(r['refl']['hkl']))}</td>"
            f"<td>{gbcos:.3f}</td>"
            f"<td><span class='bar' style='width:{width}px'></span></td>"
            f"<td class='b-{_htmllib.escape(band)}'>{_htmllib.escape(band)}</td>"
            "</tr>"
        )
    return (
        "<div class='vis'><table>"
        "<tr><th>reflection (hkl)</th><th>g&middot;b</th><th></th><th>visibility</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def _matrix_body(result: dict[str, Any]) -> str:
    systems = result.get("systems", [])
    head = ["<th>reflection</th>"]
    for s in systems:
        label = f"{_hkl_str(s['burgers'])} ({_hkl_str(s['plane'])})"
        head.append(f"<th title='{_htmllib.escape(str(s['family']))}'>{_htmllib.escape(label)}</th>")
    body_rows = []
    for row in result.get("matrix_rows", []):
        cells = [f"<td>{_htmllib.escape(_hkl_str(row['refl']['hkl']))}</td>"]
        for c in row["cells"]:
            v = float(c)
            # pink shade proportional to gb_cos (0 = dark/invisible, 1 = bright).
            bg = f"background:rgba(224,69,123,{v:.3f})"
            cells.append(f"<td class='cell' style='{bg}'>{v:.2f}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    legend = (
        "<div class='legend'>Cell shade &prop; |g&middot;b|; a near-black cell is "
        f"below the {result.get('threshold_deg')}&deg; invisibility threshold "
        "(g&perp;b).</div>"
    )
    return (
        "<div class='vis'>" + legend + "<div class='heat'><table>"
        "<tr>" + "".join(head) + "</tr>" + "".join(body_rows) + "</table></div></div>"
    )


def build_visibility_html(result: dict[str, Any]) -> str:
    """A self-contained visibility artifact: a ranked table (defect mode) or a
    reflection x slip-system heatmap (matrix mode), plus a caveats footer.

    ``result`` is ``dataclasses.asdict(VisibilityResult)``. Inline CSS only, NO
    external origins; all text html-escaped; the embedded JSON blob is `</`-guarded.
    """
    body = _defect_body(result) if result.get("mode") == "defect" else _matrix_body(result)
    caveats = "".join(f"<li>{_htmllib.escape(str(c))}</li>" for c in result.get("caveats", []))
    blob = json.dumps(result).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DFXM dislocation visibility</title>
<style>{_CSS}{_VIS_CSS}</style></head>
<body><div class="wrap">
  <h1>DFXM dislocation visibility &mdash; g&middot;b ranking</h1>
  <div class="read">{_vis_caption(result)}</div>
  {body}
  <div class="foot"><b>Caveats</b><ul>{caveats}</ul></div>
</div>
<script type="application/json" id="dfxm-vis">{blob}</script>
</body></html>
"""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ui_visibility_html.py -q`
Expected: PASS.

- [ ] **Step 5: Static gates + commit**

Run: `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` (0 errors) and `.venv/Scripts/python.exe -m ruff check src tests` (clean).

```bash
git add src/dfxm_geo_mcp/ui/forward_html.py tests/test_ui_visibility_html.py
git commit -m "feat: build_visibility_html — self-contained defect table + matrix heatmap"
```

---

## Task 7: `server.py` wiring — the `predict_visibility` MCP tool

**Files:**
- Modify: `src/dfxm_geo_mcp/server.py` (import the op; register the tool)
- Test: `tests/test_server_visibility.py` (new)

**Interfaces:**
- Consumes: Task 2 `runtime.resolve_output_path`, Task 5 `ops.visibility.predict_visibility`, Task 6 `ui.forward_html.build_visibility_html`.
- Produces: the `predict_visibility` MCP tool returning `{**dataclasses.asdict(result), "html_path": <resolved abs path>}`.

- [ ] **Step 1: Write the failing server tests**

Create `tests/test_server_visibility.py`:

```python
"""The predict_visibility MCP tool: structured dict + self-contained HTML."""

from __future__ import annotations

import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp


@pytest.mark.asyncio
async def test_predict_visibility_tool_is_registered():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert "predict_visibility" in names


@pytest.mark.asyncio
async def test_predict_visibility_defect_mode_writes_html_and_returns_sorted_rows(tmp_path):
    out = tmp_path / "vis.html"
    async with Client(mcp) as client:
        result = await client.call_tool(
            "predict_visibility",
            {"toml_text": "", "burgers": [1, -1, 0], "hkl_max": 2, "output_path": str(out)},
        )
    data = result.data
    assert data["mode"] == "defect"
    assert data["html_path"] == str(out.resolve())
    cosines = [r["gb_cos"] for r in data["defect_rows"]]
    assert cosines == sorted(cosines, reverse=True)
    # HTML artifact written and self-contained
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "http://" not in text and "https://" not in text


@pytest.mark.asyncio
async def test_predict_visibility_matrix_mode_default_path(tmp_path, monkeypatch):
    from dfxm_geo_mcp import runtime

    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    async with Client(mcp) as client:
        result = await client.call_tool("predict_visibility", {"toml_text": "", "hkl_max": 2})
    data = result.data
    assert data["mode"] == "matrix"
    assert len(data["systems"]) == 12
    saved = tmp_path / "previews" / "visibility.html"
    assert saved.exists()
    assert data["html_path"] == str(saved.resolve())


@pytest.mark.asyncio
async def test_predict_visibility_rejects_bad_args():
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.call_tool("predict_visibility", {"toml_text": "", "hkl_max": 0})
        with pytest.raises(Exception):
            await client.call_tool("predict_visibility", {"toml_text": "", "threshold_deg": 95.0})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_visibility.py -q`
Expected: FAIL — the tool is not registered (`predict_visibility` absent from `list_tools`).

- [ ] **Step 3: Wire the tool into `server.py`**

Add the op import next to the other ops imports (after `from dfxm_geo_mcp.ops import scaffold as _scaffold`):

```python
from dfxm_geo_mcp.ops import visibility as _visibility
```

Then add this tool registration (place it after the `find_reflections` tool, near line 63):

```python
@mcp.tool(annotations={"title": "Predict visibility", "readOnlyHint": True, "idempotentHint": True})
def predict_visibility(
    toml_text: str,
    burgers: list[int] | None = None,
    slip_families: list[str] | None = None,
    hkl_max: int = 3,
    threshold_deg: float = 10.0,
    output_path: str | None = None,
) -> dict:
    """Score how visible a dislocation is in each Laue-reachable reflection (g.b).

    Two modes: pass ``burgers`` (a 3-int Miller direction) to RANK reflections for
    that one defect; omit it for a reflection x slip-system MATRIX of the crystal's
    structure. Writes a self-contained HTML artifact (a ranked table or a heatmap)
    and reports its ``html_path`` alongside the structured scores. Pass
    ``slip_families`` to narrow the matrix (HCP friendly names like "basal" or the
    registry strings; e.g. "{111}<110>"). g.b = 0 is screw-exact invisibility;
    edge dislocations can retain residual contrast (see the result's caveats).

    ALWAYS tell the user the saved .html path so they can open it.
    """
    if not 1 <= hkl_max <= 6:
        raise ValueError(f"hkl_max must be between 1 and 6 (got {hkl_max})")
    if not 0.0 < threshold_deg < 90.0:
        raise ValueError(f"threshold_deg must be in (0, 90) (got {threshold_deg})")
    b = tuple(burgers) if burgers else None
    result = _visibility.predict_visibility(
        toml_text,
        burgers=b,
        slip_families=slip_families,
        hkl_max=hkl_max,
        threshold_deg=threshold_deg,
    )
    result_dict = dataclasses.asdict(result)
    html = _html.build_visibility_html(result_dict)
    path = runtime.resolve_output_path(
        output_path,
        default=runtime.cache_dir() / "previews" / "visibility.html",
        suffix=".html",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return {**result_dict, "html_path": str(path.resolve())}
```

- [ ] **Step 4: Run the server tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_server_visibility.py -q`
Expected: PASS.

- [ ] **Step 5: Update the server INSTRUCTIONS string**

Append a sentence to the `INSTRUCTIONS` string in `server.py` (after the `run_rocking` sentence) so the agent knows the tool exists:

```python
    "Before a beamtime, call predict_visibility to check whether the planned "
    "reflection will even show a defect: pass burgers (a 3-int Miller direction) "
    "to rank reachable reflections by g.b for that defect, or omit it for a "
    "reflection x slip-system visibility matrix. It writes a self-contained HTML "
    "table/heatmap and reports its .html path — ALWAYS give the user that path. "
```

- [ ] **Step 6: Full gate — all tests + static checks**

Run the whole fast suite and the static gates:

```bash
.venv/Scripts/python.exe -m pytest -q -m "not slow"
.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/
.venv/Scripts/python.exe -m ruff check src tests
```

Expected: all tests pass (the original 85 plus the new visibility/path/types/html/server tests), mypy 0 errors, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add src/dfxm_geo_mcp/server.py tests/test_server_visibility.py
git commit -m "feat: predict_visibility MCP tool (structured scores + self-contained HTML)"
```

---

## Final verification (run once after Task 7)

- [ ] **Full suite incl. slow tests** (the forward-sim writers are `@slow`): `.venv/Scripts/python.exe -m pytest -q`
- [ ] **mypy:** `.venv/Scripts/python.exe -m mypy src/dfxm_geo_mcp/` → 0 errors.
- [ ] **ruff:** `.venv/Scripts/python.exe -m ruff check src tests` → clean.
- [ ] **Wheel import (fix A regression):** re-run Task 1 Step 2's wheel-build + fresh-venv import.

## Notes for the implementer

- **Two tasks edit one file each in sequence** (Task 4 then Task 5 both edit `ops/visibility.py`; Task 2 then Task 7 both edit `server.py`). Execute them in order — do not parallelize same-file edits.
- **Tasks 1, 2, 3, 4 are mutually independent** (no shared state). Tasks 5 depends on 3+4; Task 6 depends on 3 (the dict shape); Task 7 depends on 2+5+6.
- **The matrix-mode "no registered slip systems" error branch is defensive/unreachable** through a normal mount (`resolved_structure_type` only returns fcc/bcc/hcp, all registered). It is implemented (Task 5) but not unit-tested; leave it as the documented guard.
- **Do not** add a `resolved_poisson_ratio` read anywhere — it would trip the non-FCC Poisson gate (see Global Constraints).
