"""run_rocking: a bounded analytic φ rocking scan that keeps every frame.

Unlike ``run_forward`` (single frame / max-projected), this runs a *centered* φ
scan (value=0, range=phi_max) so frame 0 is one weak-beam tail and the last frame
is the other, computes the per-frame integrated-intensity rocking curve, and
renders each frame on a SHARED color scale (so brightness genuinely tracks the
curve rather than each frame self-normalizing). The result feeds the interactive
HTML viewer (``ui.forward_html.build_rocking_html``).
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
    """Run a bounded centered φ rocking scan and return per-frame data + the curve.

    Args:
        toml_text: TOML config (empty string uses library defaults: Al 111 @ 17 keV).
            Any ``[scan.*]`` blocks in the config are overridden — a single centered
            ``[scan.phi]`` scan is imposed so frame ordering is a plain linspace.
        n_frames: number of φ samples (>= 2, <= caps["max_frames"]).
        phi_max: φ half-range in radians (> 0); the scan runs [-phi_max, +phi_max].
        caps: cap dict with keys max_npixels, max_nsub, max_frames.

    Returns:
        RockingResult with one PNG per φ (shared color scale), the φ array, the
        per-frame integrated-intensity rocking curve, the shared vmin/vmax, and meta.

    Raises:
        ValueError: invalid config, n_frames out of range, phi_max <= 0, or an
            explicitly over-cap Npixels.
    """
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
            f"Npixels={user_npixels} exceeds the preview cap ({caps['max_npixels']}). "
            f"Run production sizes with the dfxm-forward CLI."
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

        # Impose a single centered φ scan; fix every other axis so the frame order
        # is a plain ascending linspace over [-phi_max, +phi_max].
        phi_axis = dataclasses.replace(config.scan.phi, value=0.0, range=phi_max, steps=n_frames)
        fixed = {
            ax: dataclasses.replace(getattr(config.scan, ax), range=None, steps=None)
            for ax in ("chi", "two_dtheta", "z")
        }
        config.scan = dataclasses.replace(config.scan, phi=phi_axis, **fixed)

        # Force the kernel-free analytic backend (preview only).
        config.reciprocal.backend = "analytic"
        config.reciprocal.beamstop = False

        out_dir = Path(d) / "out"
        t0 = time.perf_counter()
        # See ops.forward: redirect the sim's stdout/stderr to an inert sink so the
        # stdio JSON-RPC channel stays pristine.
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
    frames_png = [
        _render_png(frames[i], aspect=aspect, vmin=vmin, vmax=vmax) for i in range(n_frames)
    ]

    resolved = report.resolved
    meta: dict = {
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
