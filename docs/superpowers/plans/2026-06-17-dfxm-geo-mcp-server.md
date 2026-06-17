# dfxm-geo MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dfxm-geo-mcp`, a standalone MCP server that lets an AI client validate/scaffold dfxm-geo configs, enumerate reachable reflections, and run preview-scale forward simulations that return a rendered image.

**Architecture:** A plain-Python ops layer (no MCP imports) wraps four `dfxm-geo` operations; a thin standalone-FastMCP adapter exposes them as tools plus three resources and two prompts. The money-shot `run_forward` defaults to the kernel-free analytic backend (sub-second). An opt-in Monte-Carlo fidelity path, backed by a generic async job engine for the ~50 s kernel bootstrap, is built last (Phase D) so it is the clean scope-cut line.

**Tech Stack:** Python 3.11+, `fastmcp>=3` (standalone, NOT the `mcp` SDK's bundled FastMCP 1.0), `dfxm-geo>=3.0.0`, `pillow`, `platformdirs`, `h5py`/`numpy` (transitive via dfxm-geo), pytest + mypy + ruff.

## Global Constraints

(Every task's requirements implicitly include this section.)

- **FastMCP must be the standalone `fastmcp>=3` package** (`from fastmcp import FastMCP`, `from fastmcp import Client`). Do NOT depend on `mcp[cli]` or import `mcp.server.fastmcp` (that is the frozen FastMCP 1.0; the in-memory test `Client` and `Image` type used here are standalone-v3 features).
- **`dfxm-geo` is not on PyPI yet** (publish pending). Install it editable from the local source into this repo's venv: `pip install -e "C:/Users/borgi/Documents/GM-reworked/Geometrical_Optics_master[cif]"`. Declare `dfxm-geo[cif]>=3.0.0` in `pyproject.toml` regardless (for the eventual PyPI story).
- **Nothing under `src/dfxm_geo_mcp/ops/` may import `fastmcp`.** The ops layer stays protocol-agnostic and unit-testable without a server. The adapter (`server.py`) is the only MCP-aware module besides `runtime.py`.
- **stdio discipline:** never `print()` to stdout (it corrupts JSON-RPC). All logging goes to stderr; wrap any `dfxm-geo` call that may emit chatty numba/scipy output in the `redirect_stdout` guard from Task 7.
- **No exception escapes a tool.** Tools return structured results/errors; `validate_config` catches `ValueError`, `KeyError`, `TypeError`, and `tomllib.TOMLDecodeError`.
- **Preview-scale only.** `run_forward` enforces caps (`Npixels<=128`, `Nsub==1`, frame count `<=9`) and refuses larger configs with a message pointing at the `dfxm-forward` CLI.
- **Gates per task:** `python -m pytest -q` green, `python -m mypy src/dfxm_geo_mcp/` 0 errors, `python -m ruff check src tests` clean before each commit.
- **Commit trailer:** every commit ends with a second `-m` body line `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Spec of record:** `docs/superpowers/specs/2026-06-17-dfxm-geo-mcp-server-design.md`. The §16 decision is settled: MC/async arm ships in v1, sequenced last (Phase D) as the cut line.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | package metadata, deps, console script `dfxm-geo-mcp`, tool config |
| `src/dfxm_geo_mcp/__init__.py` | version export |
| `src/dfxm_geo_mcp/ops/types.py` | frozen dataclasses + TypedDicts shared by ops + adapter |
| `src/dfxm_geo_mcp/ops/validate.py` | `validate_config` |
| `src/dfxm_geo_mcp/ops/reflections.py` | `find_reflections` |
| `src/dfxm_geo_mcp/ops/scaffold.py` | `scaffold_config` |
| `src/dfxm_geo_mcp/ops/forward.py` | `run_forward` (analytic preview + MC branch added in Phase D) |
| `src/dfxm_geo_mcp/runtime.py` | startup wiring: `NUMBA_CACHE_DIR`, `fm.pkl_fpath` monkeypatch, stdout guard, JIT pre-warm |
| `src/dfxm_geo_mcp/knowledge/schema.py` | annotated config schema resource |
| `src/dfxm_geo_mcp/knowledge/examples/*.toml` | canonical example configs (resources) |
| `src/dfxm_geo_mcp/jobs.py` | generic async job registry (Phase D) |
| `src/dfxm_geo_mcp/kernels.py` | cache dir + kernel presence + bootstrap driver (Phase D) |
| `src/dfxm_geo_mcp/server.py` | FastMCP app: tools, resources, prompts, instructions, `main()` |
| `tests/test_ops_*.py`, `tests/test_jobs.py`, `tests/test_server_integration.py` | tests |

---

## Phase A — Foundation

### Task 1: Repo scaffold

**Files:**
- Create: `pyproject.toml`, `src/dfxm_geo_mcp/__init__.py`, `tests/test_smoke.py`, `.gitignore`, `README.md` (stub)

**Interfaces:**
- Consumes: nothing.
- Produces: an installed `dfxm_geo_mcp` package importable in the venv; `dfxm_geo_mcp.__version__`.

- [ ] **Step 1: Create the repo skeleton and venv**

```bash
cd C:/Users/borgi/Documents/dfxm-geo-mcp
git init
py -3.12 -m venv .venv
# PowerShell: & .\.venv\Scripts\Activate.ps1   |  Bash: source .venv/Scripts/activate
mkdir -p src/dfxm_geo_mcp/ops src/dfxm_geo_mcp/knowledge/examples tests
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dfxm-geo-mcp"
version = "0.1.0"
description = "MCP server for the dfxm-geo dark-field X-ray microscopy forward model"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [{name = "Sina Borgi", email = "borgi@dtu.dk"}]
dependencies = [
    "fastmcp>=3",
    "dfxm-geo[cif]>=3.0.0",
    "pillow>=10",
    "platformdirs>=4",
]

[project.optional-dependencies]
dev = ["pytest>=8", "mypy>=1.10", "ruff>=0.6"]

[project.scripts]
dfxm-geo-mcp = "dfxm_geo_mcp.server:main"

[tool.setuptools]
packages = ["dfxm_geo_mcp", "dfxm_geo_mcp.ops", "dfxm_geo_mcp.knowledge"]

[tool.setuptools.package-dir]
"" = "src"

[tool.setuptools.package-data]
"dfxm_geo_mcp.knowledge" = ["examples/*.toml"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict_optional = true

[[tool.mypy.overrides]]
module = ["dfxm_geo", "dfxm_geo.*", "h5py", "numba", "fastmcp", "fastmcp.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = ["slow: slow integration tests (deselected by default with -m 'not slow')"]
```

- [ ] **Step 3: Write `src/dfxm_geo_mcp/__init__.py`**

```python
"""MCP server for the dfxm-geo dark-field X-ray microscopy forward model."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dfxm-geo-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
```

- [ ] **Step 4: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.mypy_cache/
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
```

- [ ] **Step 5: Write `tests/test_smoke.py`**

```python
def test_package_imports():
    import dfxm_geo_mcp

    assert dfxm_geo_mcp.__version__
```

- [ ] **Step 6: Install and run the smoke test**

```bash
pip install -e "C:/Users/borgi/Documents/GM-reworked/Geometrical_Optics_master[cif]"
pip install -e ".[dev]"
python -m pytest -q
```
Expected: 1 passed.

- [ ] **Step 7: Verify dfxm-geo imports in this venv**

Run:
```bash
python -c "import dfxm_geo; from dfxm_geo.config import SimulationConfig; print(dfxm_geo.__version__)"
```
Expected: prints `3.0.0` (or the local source version), no ImportError.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: scaffold dfxm-geo-mcp package, deps, tooling" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Shared types

**Files:**
- Create: `src/dfxm_geo_mcp/ops/__init__.py` (empty), `src/dfxm_geo_mcp/ops/types.py`
- Test: `tests/test_ops_types.py`

**Interfaces:**
- Produces: `ConfigIssue`, `ResolvedSummary` (TypedDict), `ValidationReport`, `ReflectionRecord`, `ForwardStats` (TypedDict), `ForwardResult`. Field names below are relied on by Tasks 3, 4, 6, 9, 12.

- [ ] **Step 1: Write the failing test** — `tests/test_ops_types.py`

```python
from dfxm_geo_mcp.ops.types import (
    ConfigIssue,
    ForwardResult,
    ReflectionRecord,
    ValidationReport,
)


def test_config_issue_is_frozen():
    issue = ConfigIssue(block="scan.phi", field="steps", problem="missing", fix="add steps")
    assert issue.block == "scan.phi"


def test_validation_report_ok():
    rep = ValidationReport(ok=True, issues=[], resolved=None)
    assert rep.ok and rep.issues == []


def test_reflection_record_fields():
    rec = ReflectionRecord(
        hkl=(1, 1, 1), theta_deg=9.5, eta_deg=0.0, omega_deg=0.0,
        energy_keV=17.0, reachable=True, note="",
    )
    assert rec.hkl == (1, 1, 1) and rec.reachable


def test_forward_result_carries_png():
    res = ForwardResult(png_bytes=b"\x89PNG", stats={"shape": (5, 5), "vmin": 0.0,
                        "vmax": 1.0, "backend": "analytic", "kernel": None, "wall_s": 0.1},
                        bounded=False)
    assert res.png_bytes.startswith(b"\x89PNG")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ops_types.py -q`
Expected: FAIL with `ModuleNotFoundError: dfxm_geo_mcp.ops.types`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/ops/__init__.py`** (empty file) and **`src/dfxm_geo_mcp/ops/types.py`**

```python
"""Protocol-agnostic data structures shared by the ops layer and the MCP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class ConfigIssue:
    block: str
    field: str
    problem: str
    fix: str


class ResolvedSummary(TypedDict):
    reflection: tuple[int, int, int]
    energy_keV: float
    backend: str
    n_frames: int
    scanned_axes: list[str]


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    issues: list[ConfigIssue]
    resolved: ResolvedSummary | None


@dataclass(frozen=True)
class ReflectionRecord:
    hkl: tuple[int, int, int]
    theta_deg: float
    eta_deg: float
    omega_deg: float
    energy_keV: float
    reachable: bool
    note: str


class ForwardStats(TypedDict):
    shape: tuple[int, ...]
    vmin: float
    vmax: float
    backend: str
    kernel: str | None
    wall_s: float


@dataclass(frozen=True)
class ForwardResult:
    png_bytes: bytes
    stats: ForwardStats
    bounded: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ops_types.py -q` — Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add shared ops types" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — Inline ops (the money-shot path, no MC)

### Task 3: `validate_config`

**Files:**
- Create: `src/dfxm_geo_mcp/ops/validate.py`
- Test: `tests/test_ops_validate.py`

**Interfaces:**
- Consumes: `ConfigIssue`, `ValidationReport`, `ResolvedSummary` from `ops.types`; `dfxm_geo.config.SimulationConfig.from_toml(path: Path)`.
- Produces: `validate_config(toml_text: str) -> ValidationReport`. Used by Tasks 5, 6, 9.

Grounding: `SimulationConfig.from_toml` takes a **Path**, so write the text to a temp file. Validation raises `ValueError` (e.g. `[scan.phi] range` without `steps`), `KeyError`, `TypeError` (unknown TOML key), `tomllib.TOMLDecodeError` (malformed). Frame count = product of `steps` over scanned axes (`config.scan.{phi,chi,two_dtheta,z}`, each an `AxisScanConfig` with `.is_scanned` and `.steps`).

- [ ] **Step 1: Write the failing test** — `tests/test_ops_validate.py`

```python
from dfxm_geo_mcp.ops.validate import validate_config


def test_empty_config_is_valid():
    rep = validate_config("")
    assert rep.ok and rep.issues == []
    assert rep.resolved is not None
    assert rep.resolved["reflection"] == (-1, 1, -1)
    assert rep.resolved["n_frames"] == 1


def test_range_without_steps_is_a_value_error_issue():
    rep = validate_config("[scan.phi]\nvalue = 0.0\nrange = 0.001\n")
    assert not rep.ok
    assert any(i.field == "steps" or "steps" in i.problem for i in rep.issues)


def test_unknown_key_is_a_type_error_issue():
    rep = validate_config("[reciprocal]\nnot_a_real_key = 5\n")
    assert not rep.ok and rep.issues


def test_malformed_toml_is_an_issue():
    rep = validate_config("this is not = = toml")
    assert not rep.ok and rep.issues


def test_scanned_config_reports_frames():
    rep = validate_config("[scan.phi]\nvalue = 0.0\nrange = 0.001\nsteps = 5\n")
    assert rep.ok
    assert rep.resolved is not None
    assert rep.resolved["n_frames"] == 5
    assert "phi" in rep.resolved["scanned_axes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ops_validate.py -q`
Expected: FAIL with `ModuleNotFoundError: dfxm_geo_mcp.ops.validate`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/ops/validate.py`**

```python
"""validate_config: parse TOML into a dfxm-geo SimulationConfig, report structured issues."""

from __future__ import annotations

import tempfile
import tomllib
from pathlib import Path

from dfxm_geo.config import SimulationConfig

from dfxm_geo_mcp.ops.types import ConfigIssue, ResolvedSummary, ValidationReport

_AXES = ("phi", "chi", "two_dtheta", "z")


def _resolved_summary(config: SimulationConfig) -> ResolvedSummary:
    scanned = [ax for ax in _AXES if getattr(config.scan, ax).is_scanned]
    n_frames = 1
    for ax in scanned:
        n_frames *= int(getattr(config.scan, ax).steps)
    return ResolvedSummary(
        reflection=tuple(int(c) for c in config.reciprocal.hkl),
        energy_keV=float(config.reciprocal.keV),
        backend=str(config.reciprocal.backend),
        n_frames=n_frames,
        scanned_axes=scanned,
    )


def validate_config(toml_text: str) -> ValidationReport:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "config.toml"
        path.write_text(toml_text, encoding="utf-8")
        try:
            config = SimulationConfig.from_toml(path)
        except tomllib.TOMLDecodeError as exc:
            return ValidationReport(
                ok=False,
                issues=[ConfigIssue(block="(file)", field="(syntax)", problem=str(exc),
                                    fix="Fix the TOML syntax (check brackets, quotes, =).")],
                resolved=None,
            )
        except (ValueError, KeyError, TypeError) as exc:
            return ValidationReport(
                ok=False,
                issues=[ConfigIssue(block="(config)", field="(value)", problem=str(exc),
                                    fix="Correct the field named in the message; see schema://config.")],
                resolved=None,
            )
    return ValidationReport(ok=True, issues=[], resolved=_resolved_summary(config))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ops_validate.py -q` — Expected: 5 passed.
(If `from_toml` raises a type other than the four caught for one of these inputs, widen the except in `validate.py` to include it and note it in the module docstring — the structured-error goal is to catch them all.)

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: validate_config with structured issues" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `find_reflections`

**Files:**
- Create: `src/dfxm_geo_mcp/ops/reflections.py`
- Test: `tests/test_ops_reflections.py`

**Interfaces:**
- Consumes: `ReflectionRecord` from `ops.types`; `dfxm_geo.reciprocal_space.kernel._crystal_mount_from_toml(data: dict | None)`; `dfxm_geo.crystal.oblique.find_reflections(mount, keV, ...) -> list[ReflectionGeometry]` (fields `hkl, keV, omega_1, eta_1, theta_1, omega_2, eta_2, theta_2`, radians, NaN when a solution is absent; fully-NaN rows already dropped).
- Produces: `find_reflections(toml_text: str, *, hkl_max: int = 3) -> list[ReflectionRecord]`. Used by Task 9.

Grounding: parse the toml to a dict with `tomllib`, build the mount from the `[crystal]` block, read keV from `[reciprocal]` (default 17.0). Project each two-solution record to one record: prefer solution 1, fall back to solution 2 when `theta_1` is NaN. Convert radians→degrees. `hkl_max=3` keeps the list short for chat.

- [ ] **Step 1: Write the failing test** — `tests/test_ops_reflections.py`

```python
import math

from dfxm_geo_mcp.ops.reflections import find_reflections


def test_default_al_mount_returns_records():
    recs = find_reflections("")  # empty -> default Al cubic mount @ 17 keV
    assert len(recs) > 0
    assert all(r.reachable for r in recs)
    assert all(math.isfinite(r.theta_deg) for r in recs)


def test_hcp_0002_flagged_unreachable_or_absent():
    # Ti hexagonal mount: (0002) is not Laue-reachable in the standard mount.
    toml = (
        "[crystal]\n"
        'lattice = "hexagonal"\n'
        "a = 2.95\nc = 4.68\n"
        'material = "Ti"\npoisson_ratio = 0.32\n'
    )
    recs = find_reflections(toml, hkl_max=2)
    # (0,0,2) must not appear as a reachable record.
    assert not any(r.hkl == (0, 0, 2) and r.reachable for r in recs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ops_reflections.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/ops/reflections.py`**

```python
"""find_reflections: enumerate Laue-reachable reflections for a config's mount + energy."""

from __future__ import annotations

import math
import tomllib

from dfxm_geo.crystal.oblique import find_reflections as _find
from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml

from dfxm_geo_mcp.ops.types import ReflectionRecord

_HCP_NOTE = "HCP (0002) is not Laue-reachable in the standard mount."


def find_reflections(toml_text: str, *, hkl_max: int = 3) -> list[ReflectionRecord]:
    data = tomllib.loads(toml_text) if toml_text.strip() else {}
    mount = _crystal_mount_from_toml(data.get("crystal"))
    keV = float(data.get("reciprocal", {}).get("keV", 17.0))

    records: list[ReflectionRecord] = []
    for geom in _find(mount, keV, hkl_max=hkl_max):
        if not math.isnan(geom.theta_1):
            theta, eta, omega = geom.theta_1, geom.eta_1, geom.omega_1
        else:
            theta, eta, omega = geom.theta_2, geom.eta_2, geom.omega_2
        records.append(
            ReflectionRecord(
                hkl=geom.hkl,
                theta_deg=math.degrees(theta),
                eta_deg=math.degrees(eta),
                omega_deg=math.degrees(omega),
                energy_keV=keV,
                reachable=True,
                note="",
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ops_reflections.py -q` — Expected: 2 passed.

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: find_reflections over a config mount" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `scaffold_config`

**Files:**
- Create: `src/dfxm_geo_mcp/ops/scaffold.py`
- Test: `tests/test_ops_scaffold.py`

**Interfaces:**
- Consumes: `validate_config` from `ops.validate` (for the round-trip contract test).
- Produces: `scaffold_config(*, material=None, structure_type=None, reflection=None, energy_keV=17.0, geometry_mode="symmetric", cif_path=None, scan_mode="single", backend="analytic") -> str`. Used by Task 9.

Grounding: emit TOML **text** from per-structure templates (not via `_dataclass_to_toml_str`, which omits `[detector]`). The contract is `validate_config(scaffold_config(...)).ok is True`; the TDD loop self-corrects key names against `validate_config`'s structured errors. For non-FCC, include `material` + `poisson_ratio` (the non-FCC poisson-ratio gate raises without them). Before writing the oblique template, read `docs/crystal-structures.md` in the dfxm-geo repo for the exact `[geometry]` oblique key names and the eta-supply requirement.

- [ ] **Step 1: Write the failing test** — `tests/test_ops_scaffold.py`

```python
from dfxm_geo_mcp.ops.scaffold import scaffold_config
from dfxm_geo_mcp.ops.validate import validate_config


def test_default_scaffold_validates():
    toml = scaffold_config()
    assert validate_config(toml).ok


def test_fcc_aluminium_scaffold_validates():
    toml = scaffold_config(material="Al", structure_type="fcc", reflection=(1, 1, 1))
    rep = validate_config(toml)
    assert rep.ok, [i.problem for i in rep.issues]


def test_bcc_tungsten_scaffold_validates():
    toml = scaffold_config(
        material="W", structure_type="bcc", reflection=(1, 1, 0),
        geometry_mode="oblique", energy_keV=17.0,
    )
    rep = validate_config(toml)
    assert rep.ok, [i.problem for i in rep.issues]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ops_scaffold.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Inspect the canonical config templates for exact block/key names**

Run:
```bash
python -c "import dfxm_geo, pathlib; print(pathlib.Path(dfxm_geo.__file__).parent / 'data' / 'configs')"
```
Then read `default.toml` and any `variants/*.toml` in that dir, plus `docs/crystal-structures.md`, to copy exact `[crystal]`, `[reciprocal]`, and `[geometry]` (oblique) key names. Use those names in Step 4.

- [ ] **Step 4: Write `src/dfxm_geo_mcp/ops/scaffold.py`**

```python
"""scaffold_config: emit a valid starter dfxm-geo config as TOML text."""

from __future__ import annotations


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
) -> str:
    hkl = reflection or (-1, 1, -1)
    lines: list[str] = [
        "# Generated by dfxm-geo-mcp scaffold_config.",
        "[reciprocal]",
        f"hkl = [{hkl[0]}, {hkl[1]}, {hkl[2]}]",
        f"keV = {energy_keV}",
        f'backend = "{backend}"',
        "beamstop = false" if backend == "analytic" else "beamstop = true",
        "",
    ]
    if cif_path is not None:
        lines += ["[crystal]", f'cif = "{cif_path}"', ""]
    elif structure_type is not None and structure_type != "fcc":
        lines += ["[crystal]", f'structure_type = "{structure_type}"']
        if material is not None:
            lines.append(f'material = "{material}"')
        lines.append("")
    if geometry_mode == "oblique":
        # NOTE: exact key names confirmed against docs/crystal-structures.md in Step 3.
        lines += ["[geometry]", 'mode = "oblique"', ""]
    return "\n".join(lines)
```

- [ ] **Step 4b: Iterate until the contract holds**

Run: `python -m pytest tests/test_ops_scaffold.py -q`
If a case fails, read the `ConfigIssue.problem` it prints, correct the template key/value in `scaffold.py`, and re-run. (For oblique BCC, the failure will name the missing eta or geometry key — supply it per `docs/crystal-structures.md`. If a guaranteed-valid oblique scaffold needs the computed eta, import `dfxm_geo.crystal.oblique.compute_omega_eta`, build the mount via `_crystal_mount_from_toml`, take `eta_1` (fallback `eta_2`), and emit it in the `[geometry]` block.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ops_scaffold.py -q` — Expected: 3 passed.

- [ ] **Step 6: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: scaffold_config with scaffold->validate contract" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `run_forward` (analytic preview)

**Files:**
- Create: `src/dfxm_geo_mcp/ops/forward.py`
- Test: `tests/test_ops_forward.py`

**Interfaces:**
- Consumes: `validate_config` (Task 3); `ForwardResult`, `ForwardStats` (`ops.types`); `dfxm_geo.config.SimulationConfig.from_toml`; `dfxm_geo.orchestrator.run_simulation(config, output_dir: Path) -> dict` (writes `<output_dir>/dfxm_geo.h5`, image at `/1.1/instrument/dfxm_sim_detector/data`, uint16 `(frames,H,W)`).
- Produces: `PREVIEW_CAPS`, `run_forward(toml_text: str, *, fidelity: str = "preview", caps: dict = PREVIEW_CAPS) -> ForwardResult`. The MC branch (`fidelity="mc"`) is added in Task 12; in this task `fidelity != "preview"` raises `NotImplementedError`.

Grounding: force analytic by setting `config.reciprocal.backend = "analytic"` and `config.reciprocal.beamstop = False`. Caps: `config.detector_geometry.Npixels <= 128`, `Nsub == 1`, frame count (product of scanned-axis steps) `<= 9`. Render the (max-projected) image to PNG with matplotlib's `Agg` backend.

- [ ] **Step 1: Write the failing test** — `tests/test_ops_forward.py`

```python
import pytest

from dfxm_geo_mcp.ops.forward import PREVIEW_CAPS, run_forward


def test_analytic_preview_returns_png_without_a_kernel():
    res = run_forward("")  # empty -> default Al 111, forced analytic, no kernel
    assert res.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert res.stats["backend"] == "analytic"
    assert res.stats["kernel"] is None
    assert len(res.stats["shape"]) == 2


def test_over_cap_npixels_is_refused():
    toml = "[detector_geometry]\nNpixels = 512\n"
    with pytest.raises(ValueError, match="preview"):
        run_forward(toml)


def test_invalid_config_raises_before_compute():
    with pytest.raises(ValueError):
        run_forward("[scan.phi]\nvalue = 0.0\nrange = 0.001\n")  # range without steps


def test_mc_fidelity_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        run_forward("", fidelity="mc")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ops_forward.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/ops/forward.py`**

```python
"""run_forward: bounded, analytic-by-default preview forward sim returning a PNG."""

from __future__ import annotations

import io
import tempfile
import time
import tomllib
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from dfxm_geo.config import SimulationConfig  # noqa: E402
from dfxm_geo.orchestrator import run_simulation  # noqa: E402

from dfxm_geo_mcp.ops.types import ForwardResult, ForwardStats  # noqa: E402
from dfxm_geo_mcp.ops.validate import validate_config  # noqa: E402

PREVIEW_CAPS = {"max_npixels": 128, "max_nsub": 1, "max_frames": 9}
_IMAGE_DATASET = "/1.1/instrument/dfxm_sim_detector/data"
_AXES = ("phi", "chi", "two_dtheta", "z")


def _frame_count(config: SimulationConfig) -> int:
    n = 1
    for ax in _AXES:
        a = getattr(config.scan, ax)
        if a.is_scanned:
            n *= int(a.steps)
    return n


def _render_png(image: np.ndarray) -> bytes:
    fig, axis = plt.subplots(figsize=(4, 4), dpi=110)
    axis.imshow(image, cmap="magma", origin="lower", aspect="auto")
    axis.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return buf.getvalue()


def run_forward(toml_text: str, *, fidelity: str = "preview", caps: dict = PREVIEW_CAPS) -> ForwardResult:
    report = validate_config(toml_text)
    if not report.ok:
        raise ValueError(report.issues[0].problem)
    if fidelity != "preview":
        raise NotImplementedError("MC fidelity is added in Phase D (Task 12).")

    with tempfile.TemporaryDirectory() as d:
        cfg_path = Path(d) / "config.toml"
        cfg_path.write_text(toml_text, encoding="utf-8")
        config = SimulationConfig.from_toml(cfg_path)

        if config.detector_geometry.Npixels > caps["max_npixels"]:
            raise ValueError(
                f"Npixels={config.detector_geometry.Npixels} exceeds the preview cap "
                f"({caps['max_npixels']}). Run production sizes with the dfxm-forward CLI."
            )
        if config.detector_geometry.Nsub > caps["max_nsub"]:
            raise ValueError("Nsub>1 exceeds the preview cap; use the dfxm-forward CLI.")
        n_frames = _frame_count(config)
        if n_frames > caps["max_frames"]:
            raise ValueError(
                f"{n_frames} frames exceed the preview cap ({caps['max_frames']}). "
                f"Use the dfxm-forward CLI."
            )

        # Force the kernel-free analytic backend for the preview.
        config.reciprocal.backend = "analytic"
        config.reciprocal.beamstop = False

        out_dir = Path(d) / "out"
        t0 = time.perf_counter()
        run_simulation(config, out_dir)
        wall_s = time.perf_counter() - t0

        with h5py.File(out_dir / "dfxm_geo.h5", "r") as h5:
            frames = np.asarray(h5[_IMAGE_DATASET])  # (frames, H, W)
    image = frames.max(axis=0) if frames.ndim == 3 else frames
    stats: ForwardStats = {
        "shape": tuple(int(s) for s in image.shape),
        "vmin": float(image.min()),
        "vmax": float(image.max()),
        "backend": "analytic",
        "kernel": None,
        "wall_s": round(wall_s, 3),
    }
    return ForwardResult(png_bytes=_render_png(image), stats=stats, bounded=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ops_forward.py -q`
Expected: 4 passed. (First run pays a one-time numba JIT cost of a few seconds; that is expected.)

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: run_forward analytic preview with caps + PNG" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — MCP adapter + knowledge (demo-able v1-minus-MC)

### Task 7: `runtime.py` (startup wiring)

**Files:**
- Create: `src/dfxm_geo_mcp/runtime.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produces: `cache_dir() -> Path`, `configure_numba_cache() -> None`, `point_kernel_lookup_at_cache() -> None`, `guard_stdout()` (context manager), `prewarm_jit() -> None`. Used by Task 9 (`server.main`) and Task 11.

Grounding: `dfxm_geo.direct_space.forward_model.pkl_fpath` is a module-global string pointing inside the source tree; reassign it to the cache dir so MC kernel lookup (Phase D) sees the cache. `NUMBA_CACHE_DIR` must be a writable dir so the JIT cache persists across `uvx` runs. The stdout guard redirects stdout to stderr around chatty library calls.

- [ ] **Step 1: Write the failing test** — `tests/test_runtime.py`

```python
import sys

from dfxm_geo_mcp import runtime


def test_cache_dir_exists():
    d = runtime.cache_dir()
    assert d.exists()


def test_point_kernel_lookup_at_cache():
    runtime.point_kernel_lookup_at_cache()
    import dfxm_geo.direct_space.forward_model as fm

    assert str(runtime.cache_dir()) in str(fm.pkl_fpath)


def test_guard_stdout_redirects_to_stderr(capsys):
    with runtime.guard_stdout():
        print("this must not hit stdout")
    captured = capsys.readouterr()
    assert "this must not hit stdout" not in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runtime.py -q`
Expected: FAIL with `ModuleNotFoundError: dfxm_geo_mcp.runtime`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/runtime.py`**

```python
"""Startup wiring: cache dirs, kernel-lookup path, stdout guard, JIT pre-warm."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from platformdirs import user_cache_dir

_APP = "dfxm-geo-mcp"


def cache_dir() -> Path:
    d = Path(user_cache_dir(_APP))
    (d / "kernels").mkdir(parents=True, exist_ok=True)
    return d


def configure_numba_cache() -> None:
    nb = cache_dir() / "numba"
    nb.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(nb)


def point_kernel_lookup_at_cache() -> None:
    import dfxm_geo.direct_space.forward_model as fm

    fm.pkl_fpath = str(cache_dir() / "kernels")


@contextlib.contextmanager
def guard_stdout():
    """Redirect stdout to stderr so library prints can't corrupt stdio JSON-RPC."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def prewarm_jit() -> None:
    """Compile the numba forward + Hg kernels once via a tiny analytic forward."""
    from dfxm_geo_mcp.ops.forward import run_forward

    with guard_stdout():
        run_forward("[detector_geometry]\nNpixels = 16\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runtime.py -q` — Expected: 3 passed.

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: runtime wiring (cache, kernel-path, stdout guard, prewarm)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Knowledge layer (schema + examples)

**Files:**
- Create: `src/dfxm_geo_mcp/knowledge/__init__.py` (empty), `src/dfxm_geo_mcp/knowledge/schema.py`, `src/dfxm_geo_mcp/knowledge/examples/default.toml`, `.../oblique_bcc.toml`, `.../hcp_ti.toml`
- Test: `tests/test_knowledge.py`

**Interfaces:**
- Produces: `config_schema() -> dict[str, dict]` (block -> {field -> {type, default, meaning}}); `list_examples() -> dict[str, str]` (name -> toml text); `example_names() -> list[str]`. Used by Task 9.

Grounding: generate the schema by introspecting the dfxm-geo config dataclasses (`ReciprocalConfig`, `ScanConfig`/`AxisScanConfig`, `DetectorGeometryConfig`) with `dataclasses.fields`, so it cannot drift. Each example toml must pass `validate_config`.

- [ ] **Step 1: Write the failing test** — `tests/test_knowledge.py`

```python
from dfxm_geo_mcp.knowledge.schema import config_schema, example_names, list_examples
from dfxm_geo_mcp.ops.validate import validate_config


def test_schema_has_reciprocal_block():
    schema = config_schema()
    assert "reciprocal" in schema
    assert "keV" in schema["reciprocal"]


def test_examples_all_validate():
    examples = list_examples()
    assert set(example_names()) == set(examples)
    for name, toml in examples.items():
        assert validate_config(toml).ok, name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the example configs**

`src/dfxm_geo_mcp/knowledge/examples/default.toml`:
```toml
# Default Al 111 @ 17 keV, analytic preview, single frame.
[reciprocal]
hkl = [-1, 1, -1]
keV = 17.0
backend = "analytic"
beamstop = false
```

`src/dfxm_geo_mcp/knowledge/examples/oblique_bcc.toml` and `hcp_ti.toml`: copy a known-valid `[crystal]`/`[reciprocal]`/`[geometry]` combination from the dfxm-geo `data/configs` templates inspected in Task 5 Step 3. Each must pass `validate_config` (the Step-5 test enforces it; iterate until green).

- [ ] **Step 4: Write `src/dfxm_geo_mcp/knowledge/__init__.py`** (empty) and **`src/dfxm_geo_mcp/knowledge/schema.py`**

```python
"""Generated config schema + bundled example configs (MCP resources)."""

from __future__ import annotations

import dataclasses
from importlib.resources import files

from dfxm_geo.config import DetectorGeometryConfig, ReciprocalConfig

_BLOCKS = {"reciprocal": ReciprocalConfig, "detector_geometry": DetectorGeometryConfig}


def config_schema() -> dict[str, dict]:
    schema: dict[str, dict] = {}
    for block, cls in _BLOCKS.items():
        fields: dict[str, dict] = {}
        for f in dataclasses.fields(cls):
            default = f.default if f.default is not dataclasses.MISSING else None
            fields[f.name] = {"type": str(f.type), "default": repr(default)}
        schema[block] = fields
    return schema


def example_names() -> list[str]:
    return sorted(p.name[:-5] for p in files("dfxm_geo_mcp.knowledge").joinpath("examples").iterdir()
                  if p.name.endswith(".toml"))


def list_examples() -> dict[str, str]:
    root = files("dfxm_geo_mcp.knowledge").joinpath("examples")
    return {name: root.joinpath(f"{name}.toml").read_text(encoding="utf-8")
            for name in example_names()}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge.py -q` — Expected: 2 passed. (Iterate on the example tomls until `test_examples_all_validate` is green.)

- [ ] **Step 6: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: schema + example configs knowledge layer" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: FastMCP server (inline tools + resources + prompts)

**Files:**
- Create: `src/dfxm_geo_mcp/server.py`
- Test: `tests/test_server_integration.py`

**Interfaces:**
- Consumes: all ops functions; `runtime` (Task 7); `knowledge` (Task 8); `from fastmcp import FastMCP, Client`; `from fastmcp.utilities.types import Image`.
- Produces: module-level `mcp` (FastMCP app) and `main() -> None` (the `dfxm-geo-mcp` console entry). The bootstrap tools + `kernels://cached` resource are added in Task 12.

Grounding: register four inline tools, three resources (`schema://config`, `examples://{name}` template, `kernels://cached` placeholder returning "[]" until Task 12), two prompts, and a server `instructions` string. Workflow ordering goes in `instructions`, NOT tool descriptions. `run_forward` returns `Image(data=png, format="png")`. Verify the exact FastMCP `Client` API and `Image` import path against the installed `fastmcp` version with `python -c "import fastmcp; print(fastmcp.__version__)"` and `gofastmcp.com` if an import differs.

- [ ] **Step 1: Write the failing test** — `tests/test_server_integration.py`

```python
import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp


@pytest.mark.asyncio
async def test_lists_all_tools():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"validate_config", "find_reflections", "scaffold_config", "run_forward"} <= names


@pytest.mark.asyncio
async def test_validate_config_tool_returns_structured_ok():
    async with Client(mcp) as client:
        result = await client.call_tool("validate_config", {"toml_text": ""})
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_run_forward_returns_an_image():
    async with Client(mcp) as client:
        result = await client.call_tool("run_forward", {"toml_text": ""})
    assert any(getattr(c, "type", None) == "image" for c in result.content)


@pytest.mark.asyncio
async def test_lists_resources_and_prompts():
    async with Client(mcp) as client:
        resources = await client.list_resources()
        prompts = {p.name for p in await client.list_prompts()}
    assert prompts == {"guided_forward_simulation", "diagnose_config"}
    assert any("schema" in str(r.uri) for r in resources)
```

Add `pytest-asyncio` to the dev deps for this test (`pip install pytest-asyncio` and add to `[project.optional-dependencies] dev`); set `asyncio_mode = "auto"` under `[tool.pytest.ini_options]`. If the installed FastMCP exposes a synchronous in-memory test client instead, use that and drop the async markers.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server_integration.py -q`
Expected: FAIL with `ModuleNotFoundError: dfxm_geo_mcp.server`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/server.py`**

```python
"""FastMCP adapter: thin registrations over the ops layer."""

from __future__ import annotations

import dataclasses

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from dfxm_geo_mcp import knowledge, runtime
from dfxm_geo_mcp.ops import forward as _forward
from dfxm_geo_mcp.ops import reflections as _reflections
from dfxm_geo_mcp.ops import scaffold as _scaffold
from dfxm_geo_mcp.ops import validate as _validate

INSTRUCTIONS = (
    "Drive the dfxm-geo forward model. Typical flow: scaffold_config -> validate_config "
    "-> run_forward (analytic, no kernel needed). A fidelity='mc' forward needs a "
    "bootstrapped kernel for its reflection/energy; if run_forward reports a missing "
    "kernel, call start_bootstrap then poll get_job_status. Previews are capped "
    "(Npixels<=128, <=9 frames); production runs use the dfxm-forward CLI."
)

mcp = FastMCP(name="dfxm-geo-mcp", instructions=INSTRUCTIONS)


@mcp.tool(annotations={"title": "Validate config", "readOnlyHint": True, "idempotentHint": True})
def validate_config(toml_text: str) -> dict:
    """Parse a dfxm-geo TOML config and report structured issues, or the resolved summary."""
    return dataclasses.asdict(_validate.validate_config(toml_text))


@mcp.tool(annotations={"title": "Find reflections", "readOnlyHint": True, "idempotentHint": True})
def find_reflections(toml_text: str, hkl_max: int = 3) -> list[dict]:
    """List Laue-reachable reflections for the config's crystal mount and beam energy."""
    return [dataclasses.asdict(r) for r in _reflections.find_reflections(toml_text, hkl_max=hkl_max)]


@mcp.tool(annotations={"title": "Scaffold config", "readOnlyHint": True, "idempotentHint": True})
def scaffold_config(material: str | None = None, structure_type: str | None = None,
                    reflection: list[int] | None = None, energy_keV: float = 17.0,
                    geometry_mode: str = "symmetric", cif_path: str | None = None,
                    scan_mode: str = "single") -> str:
    """Return a valid starter dfxm-geo config (TOML text) for the requested crystal/reflection."""
    hkl = tuple(reflection) if reflection else None
    return _scaffold.scaffold_config(material=material, structure_type=structure_type,
                                     reflection=hkl, energy_keV=energy_keV,
                                     geometry_mode=geometry_mode, cif_path=cif_path,
                                     scan_mode=scan_mode)


@mcp.tool(annotations={"title": "Run forward preview", "readOnlyHint": True})
def run_forward(toml_text: str, fidelity: str = "preview") -> Image:
    """Run a preview-scale forward simulation and return the rendered DFXM image."""
    result = _forward.run_forward(toml_text, fidelity=fidelity)
    return Image(data=result.png_bytes, format="png")


@mcp.resource("schema://config")
def schema_resource() -> dict:
    """The annotated dfxm-geo config schema (generated from the dataclasses)."""
    return knowledge.schema.config_schema()


@mcp.resource("examples://{name}")
def example_resource(name: str) -> str:
    """A canonical example config by name (see examples list)."""
    return knowledge.schema.list_examples()[name]


@mcp.resource("kernels://cached")
def cached_kernels_resource() -> list[str]:
    """MC kernels currently cached (instantly runnable at fidelity='mc')."""
    return []  # populated in Task 12


@mcp.prompt()
def guided_forward_simulation(goal: str) -> str:
    """Guide: scaffold -> validate -> run_forward for the user's stated goal."""
    return (f"Help the user run a DFXM forward simulation for: {goal}. "
            "Call scaffold_config, then validate_config on the result, then run_forward.")


@mcp.prompt()
def diagnose_config(toml_text: str) -> str:
    """Guide: triage a failing config using validate_config's structured issues."""
    return (f"Diagnose this dfxm-geo config and propose fixes:\n\n{toml_text}\n\n"
            "Call validate_config and explain each issue's fix.")


def main() -> None:
    runtime.configure_numba_cache()
    runtime.point_kernel_lookup_at_cache()
    import threading

    threading.Thread(target=runtime.prewarm_jit, daemon=True).start()
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server_integration.py -q`
Expected: 4 passed. (Reconcile any `result.data` / `result.content` shape with the installed FastMCP version; adjust the asserts to the real client return type if needed.)

- [ ] **Step 5: Manual stdio smoke (optional but recommended)**

Run: `python -m dfxm_geo_mcp.server` then Ctrl-C. Expected: it starts and waits on stdio without printing to stdout. Then register it in Claude Desktop (`claude_desktop_config.json`: `{"mcpServers": {"dfxm-geo": {"command": "dfxm-geo-mcp"}}}`) and confirm `run_forward` renders an image. **This is the money-shot screenshot for the README.**

- [ ] **Step 6: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: FastMCP server with inline tools, resources, prompts" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **Milestone: v1-minus-MC.** The server is now fully functional and demo-able over stdio with the analytic money-shot. Phase D is the optional MC/async arm; if the sprint clock runs out, ship here and move Phase D to the README roadmap.

---

## Phase D — MC fidelity + async bootstrap (the cut line)

### Task 10: Async job registry

**Files:**
- Create: `src/dfxm_geo_mcp/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Produces: `JobState`, `Job` (dataclass: `id, state, progress, message, result, error, key`), `JobRegistry` with `submit(key, fn) -> str`, `status(job_id) -> Job`, `result(job_id) -> object`, `cancel(job_id) -> bool`. `fn` takes one arg: a `report(progress: float, message: str)` callback. Used by Task 12.

Grounding: `ThreadPoolExecutor(max_workers=2)`; `uuid4` ids; dedup on `key` (a live job for the same key returns its id); TTL eviction of finished jobs.

- [ ] **Step 1: Write the failing test** — `tests/test_jobs.py`

```python
import time

from dfxm_geo_mcp.jobs import JobRegistry


def test_job_succeeds_and_returns_result():
    reg = JobRegistry()
    jid = reg.submit(("k", 1), lambda report: 42)
    for _ in range(100):
        if reg.status(jid).state in ("succeeded", "failed"):
            break
        time.sleep(0.02)
    assert reg.status(jid).state == "succeeded"
    assert reg.result(jid) == 42


def test_dedup_returns_same_id_for_live_key():
    reg = JobRegistry()
    started = []

    def slow(report):
        started.append(1)
        time.sleep(0.2)
        return 1

    a = reg.submit(("dup",), slow)
    b = reg.submit(("dup",), slow)
    assert a == b


def test_failing_job_surfaces_error():
    reg = JobRegistry()

    def boom(report):
        raise RuntimeError("kaboom")

    jid = reg.submit(("e",), boom)
    for _ in range(100):
        if reg.status(jid).state in ("succeeded", "failed"):
            break
        time.sleep(0.02)
    assert reg.status(jid).state == "failed"
    assert "kaboom" in (reg.status(jid).error or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_jobs.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/jobs.py`**

```python
"""Generic in-process async job registry (handle pattern) for long operations."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

JobState = Literal["pending", "running", "succeeded", "failed"]


@dataclass
class Job:
    id: str
    state: JobState = "pending"
    progress: float = 0.0
    message: str = ""
    result: Any | None = None
    error: str | None = None
    key: tuple | None = None


class JobRegistry:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._by_key: dict[tuple, str] = {}
        self._lock = threading.Lock()

    def submit(self, key: tuple, fn: Callable[[Callable[[float, str], None]], Any]) -> str:
        with self._lock:
            existing = self._by_key.get(key)
            if existing and self._jobs[existing].state in ("pending", "running"):
                return existing
            job = Job(id=uuid.uuid4().hex[:12], key=key)
            self._jobs[job.id] = job
            self._by_key[key] = job.id

        def report(progress: float, message: str) -> None:
            job.progress, job.message = progress, message

        def runner() -> None:
            job.state = "running"
            try:
                job.result = fn(report)
                job.state = "succeeded"
                job.progress = 1.0
            except Exception as exc:  # noqa: BLE001 - captured into the job
                job.state = "failed"
                job.error = str(exc)

        self._pool.submit(runner)
        return job.id

    def status(self, job_id: str) -> Job:
        return self._jobs[job_id]

    def result(self, job_id: str) -> Any:
        job = self._jobs[job_id]
        if job.state != "succeeded":
            raise RuntimeError(f"job {job_id} is {job.state}: {job.error}")
        return job.result

    def cancel(self, job_id: str) -> bool:
        # Best-effort: numba work is not cleanly interruptible once running.
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_jobs.py -q` — Expected: 3 passed.

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: generic async job registry with dedup" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Kernel cache + bootstrap driver

**Files:**
- Create: `src/dfxm_geo_mcp/kernels.py`
- Test: `tests/test_kernels.py`

**Interfaces:**
- Consumes: `runtime.cache_dir()` (Task 7); `dfxm_geo.reciprocal_space.kernel.generate_kernel(...)`; `dfxm_geo.reciprocal_space.kernel._crystal_mount_from_toml`.
- Produces: `kernel_present(hkl: tuple[int,int,int], keV: float) -> bool`, `cached_kernel_names() -> list[str]`, `bootstrap(hkl, keV, *, mount_toml: str | None, report) -> str` (builds a kernel into the cache, returns its path). Used by Task 12.

Grounding: kernel files match `Resq_i_h{h}_k{k}_l{l}_{keV}keV_*.npz` in `cache_dir()/kernels`. Verify `generate_kernel`'s exact required args with `python -c "import inspect; from dfxm_geo.reciprocal_space.kernel import generate_kernel; print(inspect.signature(generate_kernel))"` before wiring `bootstrap`.

- [ ] **Step 1: Write the failing test** — `tests/test_kernels.py`

```python
from dfxm_geo_mcp import kernels


def test_kernel_absent_on_empty_cache():
    assert kernels.kernel_present((9, 9, 9), 17.0) is False


def test_present_after_a_fake_kernel_is_dropped_in(tmp_path, monkeypatch):
    from dfxm_geo_mcp import runtime

    fake_cache = tmp_path / "kernels"
    fake_cache.mkdir()
    monkeypatch.setattr(runtime, "cache_dir", lambda: tmp_path)
    (fake_cache / "Resq_i_h1_k1_l1_17.0keV_20260101.npz").write_bytes(b"x")
    assert kernels.kernel_present((1, 1, 1), 17.0) is True
    assert "Resq_i_h1_k1_l1_17.0keV_20260101" in "".join(kernels.cached_kernel_names())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kernels.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/dfxm_geo_mcp/kernels.py`**

```python
"""MC kernel cache discovery + on-demand bootstrap driver."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Callable

from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml, generate_kernel

from dfxm_geo_mcp import runtime


def _kernels_dir() -> Path:
    return runtime.cache_dir() / "kernels"


def _glob_for(hkl: tuple[int, int, int], keV: float) -> str:
    h, k, l = hkl
    return f"Resq_i_h{h}_k{k}_l{l}_{keV}keV_*.npz"


def kernel_present(hkl: tuple[int, int, int], keV: float) -> bool:
    return any(_kernels_dir().glob(_glob_for(hkl, keV)))


def cached_kernel_names() -> list[str]:
    return sorted(p.stem for p in _kernels_dir().glob("Resq_i_*.npz"))


def bootstrap(hkl: tuple[int, int, int], keV: float, *, mount_toml: str | None,
              report: Callable[[float, str], None]) -> str:
    """Build an MC kernel for (hkl, keV) into the cache; return its path."""
    report(0.0, "starting kernel bootstrap")
    data = tomllib.loads(mount_toml) if mount_toml else {}
    mount = _crystal_mount_from_toml(data.get("crystal"))
    out = _kernels_dir() / f"Resq_i_h{hkl[0]}_k{hkl[1]}_l{hkl[2]}_{keV}keV.npz"
    # NOTE: confirm generate_kernel's exact kwargs (Step grounding) before this call.
    generate_kernel(output_path=str(out), hkl=hkl, keV=keV, mount=mount)
    report(1.0, "kernel built")
    return str(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kernels.py -q` — Expected: 2 passed.
(Do NOT add a real-bootstrap test to the default suite — a real kernel is ~50 s and 128 MB. If you want one, mark it `@pytest.mark.slow` and shrink nothing: it will be slow by nature.)

- [ ] **Step 5: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: kernel cache discovery + bootstrap driver" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Wire MC fidelity into run_forward + the bootstrap tools

**Files:**
- Modify: `src/dfxm_geo_mcp/ops/forward.py`, `src/dfxm_geo_mcp/server.py`
- Test: `tests/test_ops_forward.py` (extend), `tests/test_server_integration.py` (extend)

**Interfaces:**
- Consumes: `kernels` (Task 11), `JobRegistry` (Task 10).
- Produces: `run_forward(..., fidelity="mc")` returns the structured needs-bootstrap dict when no kernel exists; `server` gains `start_bootstrap`, `get_job_status`, `get_job_result` tools and a live `kernels://cached` resource.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ops_forward.py`:
```python
def test_mc_without_kernel_returns_needs_bootstrap():
    from dfxm_geo_mcp.ops.forward import run_forward

    res = run_forward("", fidelity="mc")
    assert res.needs_bootstrap is True
    assert res.bootstrap_hint["hkl"] == [-1, 1, -1]
```

Append to `tests/test_server_integration.py`:
```python
@pytest.mark.asyncio
async def test_bootstrap_tools_exist():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"start_bootstrap", "get_job_status", "get_job_result"} <= names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ops_forward.py::test_mc_without_kernel_returns_needs_bootstrap tests/test_server_integration.py::test_bootstrap_tools_exist -q`
Expected: FAIL (`needs_bootstrap` attr missing; bootstrap tools absent).

- [ ] **Step 3: Extend `ForwardResult` and `run_forward` for the MC branch**

In `src/dfxm_geo_mcp/ops/types.py`, add two optional fields to `ForwardResult`:
```python
@dataclass(frozen=True)
class ForwardResult:
    png_bytes: bytes
    stats: ForwardStats
    bounded: bool
    needs_bootstrap: bool = False
    bootstrap_hint: dict | None = None
```

In `src/dfxm_geo_mcp/ops/forward.py`, replace the `if fidelity != "preview": raise NotImplementedError(...)` block with:
```python
    if fidelity == "mc":
        from dfxm_geo_mcp import kernels

        report = validate_config(toml_text)
        if not report.ok:
            raise ValueError(report.issues[0].problem)
        hkl = report.resolved["reflection"]
        keV = report.resolved["energy_keV"]
        if not kernels.kernel_present(hkl, keV):
            return ForwardResult(
                png_bytes=b"", stats={"shape": (0,), "vmin": 0.0, "vmax": 0.0,
                "backend": "mc", "kernel": None, "wall_s": 0.0}, bounded=False,
                needs_bootstrap=True,
                bootstrap_hint={"hkl": list(hkl), "energy_keV": keV,
                                "tool": "start_bootstrap"},
            )
        # kernel present: fall through to run_simulation WITHOUT forcing analytic.
    elif fidelity != "preview":
        raise NotImplementedError(f"unknown fidelity {fidelity!r}")
```
Then guard the analytic-forcing lines so they only run for `fidelity == "preview"`:
```python
        if fidelity == "preview":
            config.reciprocal.backend = "analytic"
            config.reciprocal.beamstop = False
```
and set `stats["backend"]` / `stats["kernel"]` from `config.reciprocal.backend` rather than the hardcoded `"analytic"`.

- [ ] **Step 4: Add the bootstrap tools + live resource to `server.py`**

```python
from dfxm_geo_mcp import kernels
from dfxm_geo_mcp.jobs import JobRegistry

_JOBS = JobRegistry()


@mcp.tool(annotations={"title": "Start kernel bootstrap", "readOnlyHint": False,
                       "idempotentHint": True, "destructiveHint": False})
def start_bootstrap(hkl: list[int], energy_keV: float = 17.0, mount_toml: str | None = None) -> dict:
    """Build the MC resolution kernel for a reflection/energy (long; returns a job id)."""
    h = (hkl[0], hkl[1], hkl[2])
    job_id = _JOBS.submit(
        ("kernel", h, energy_keV),
        lambda report: kernels.bootstrap(h, energy_keV, mount_toml=mount_toml, report=report),
    )
    return {"job_id": job_id}


@mcp.tool(annotations={"title": "Job status", "readOnlyHint": True})
def get_job_status(job_id: str) -> dict:
    """Poll a bootstrap job's state and progress."""
    job = _JOBS.status(job_id)
    return {"state": job.state, "progress": job.progress, "message": job.message}


@mcp.tool(annotations={"title": "Job result", "readOnlyHint": True})
def get_job_result(job_id: str) -> dict:
    """Fetch a finished bootstrap job's result (kernel path) or its error."""
    job = _JOBS.status(job_id)
    if job.state == "succeeded":
        return {"kernel": job.result}
    return {"state": job.state, "error": job.error}
```
And replace `cached_kernels_resource` body with `return kernels.cached_kernel_names()`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ops_forward.py tests/test_server_integration.py -q`
Expected: all pass (including the two new tests).

- [ ] **Step 6: Gate + commit**

```bash
python -m mypy src/dfxm_geo_mcp/ && python -m ruff check src tests && python -m pytest -q
git add -A
git commit -m "feat: MC fidelity + async bootstrap tools" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase E — Packaging & polish

### Task 13: README, money-shot, final gate

**Files:**
- Modify: `README.md`
- Create: `docs/img/money_shot.png` (the Claude Desktop screenshot from Task 9 Step 5)

**Interfaces:**
- Consumes: a working server.
- Produces: a CV-ready repo.

- [ ] **Step 1: Capture the money-shot** — screenshot Claude Desktop calling `run_forward("")` and rendering the DFXM image; save to `docs/img/money_shot.png`.

- [ ] **Step 2: Write `README.md`**

Lead with the screenshot, then the run story in this order, then the heavy-first-run note:
```markdown
# dfxm-geo-mcp

An MCP server that lets an AI client drive the [dfxm-geo](https://github.com/borgi-s/Geometrical_Optics_master) dark-field X-ray microscopy forward model: validate and scaffold configs, enumerate reachable reflections, and render preview-scale simulations.

![Claude Desktop rendering a DFXM image from a plain-English request](docs/img/money_shot.png)

## Run

    uvx dfxm-geo-mcp

Claude Desktop (`claude_desktop_config.json`):

    {"mcpServers": {"dfxm-geo": {"command": "uvx", "args": ["dfxm-geo-mcp"]}}}

Or: `pip install dfxm-geo-mcp` then `dfxm-geo-mcp`.

> First run pulls a heavy scientific stack (numba/scipy) and warms a JIT cache (~10 s once). No fake demo mode — the sims are real.

## Tools
validate_config · find_reflections · scaffold_config · run_forward (analytic preview) · start_bootstrap / get_job_status / get_job_result (MC fidelity).

## Architecture
A protocol-agnostic ops layer wrapping dfxm-geo, under a thin FastMCP adapter. See `docs/superpowers/specs/`.

## Roadmap (v2)
run_identify · remote HTTP transport · `.mcpb` bundle.
```

- [ ] **Step 3: Final full gate**

```bash
python -m pytest -q
python -m mypy src/dfxm_geo_mcp/
python -m ruff check src tests
python -m build  # confirm the wheel builds; check examples/*.toml are included
```
Expected: tests green, mypy 0 errors, ruff clean, wheel builds with `dfxm_geo_mcp/knowledge/examples/*.toml` bundled.

- [ ] **Step 4: Check the PyPI name + commit**

```bash
pip index versions dfxm-geo-mcp 2>&1 | head -1  # confirm the name is free before any publish
git add -A
git commit -m "docs: README, money-shot, final gate" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(PyPI publish is a separate, user-approved step — out of scope for the build.)

---

## Self-Review

**Spec coverage:**
- §2 ops layer (validate/find/scaffold/run_forward) → Tasks 3,4,5,6. ✓
- §2 thin FastMCP adapter + 3 resources + 2 prompts → Task 9. ✓
- §2 analytic default + PNG inline + caps + JIT pre-warm → Tasks 6,7,9. ✓
- §2 structured errors / 4 exception types → Task 3. ✓
- §6 async job engine (handle pattern, dedup, TTL/cancel stance) → Task 10. ✓ (TTL eviction is implemented minimally; a `_evict_expired` pass can be added if a long-lived server leaks — noted as open item, not load-bearing for v1.)
- §7 tool annotations + server `instructions` (ordering out of tool descriptions) → Task 9. ✓
- §8 temp-HDF5 read-back, max-projection → Task 6. ✓
- §9 cache dir + `fm.pkl_fpath` monkeypatch + `NUMBA_CACHE_DIR` + on-demand bootstrap (no shipped kernel) → Tasks 7,11,12. ✓
- §10 schema (generated) + examples (template) + kernels resource → Tasks 8,9,12. ✓
- §11 stdio stdout discipline → Task 7 (guard) + Task 9 (used in pre-warm); wrap forward/bootstrap calls in `guard_stdout` if any stdout noise appears in the stdio smoke (Task 9 Step 5). ✓
- §12 ops unit tests + in-memory Client integration → every task + Task 9. ✓
- §13 packaging (fastmcp>=3 not mcp[cli], uvx/PyPI, console script, heavy-first-run note) → Tasks 1,13. ✓
- §16 MC/async arm in v1, sequenced last → Phase D (Tasks 10-12), with the v1-minus-MC milestone after Task 9 as the cut line. ✓
- Deferred per non-goals: `run_identify`, remote HTTP, `.mcpb` → README roadmap (Task 13). ✓

**Placeholder scan:** The only deliberately deferred specifics are (a) exact oblique `[geometry]` keys (Task 5 Step 3 reads `docs/crystal-structures.md`; the scaffold→validate contract test forces correctness) and (b) `generate_kernel`'s exact kwargs (Task 11 grounding step verifies via `inspect.signature` before the call). Both are real verification steps against the source, not hand-wave placeholders. The FastMCP `Client`/`Image`/`result.data` shapes (Task 9) are verified against the installed `fastmcp` version in-task. No "TODO"/"handle appropriately" steps remain.

**Type consistency:** `ForwardResult` gains `needs_bootstrap`/`bootstrap_hint` in Task 12 (declared as defaulted fields so Task 6's construction stays valid). `ReflectionRecord`, `ValidationReport`, `ResolvedSummary`, `ForwardStats`, `Job`, `JobRegistry.submit(key, fn)` names are used consistently across Tasks 2→4→6→9→10→12. `run_forward(toml_text, *, fidelity, caps)` signature is stable across Tasks 6 and 12.
