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
    needs_bootstrap: bool = False
    bootstrap_hint: dict | None = None
    meta: dict | None = None


@dataclass(frozen=True)
class RockingResult:
    frames_png: list[bytes]
    phis: list[float]
    intensities: list[float]
    vmin: float
    vmax: float
    meta: dict
    bounded: bool = True


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
