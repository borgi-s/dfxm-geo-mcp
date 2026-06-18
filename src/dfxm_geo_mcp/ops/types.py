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
