"""run_forward: bounded, analytic-by-default preview forward sim returning a PNG."""

from __future__ import annotations

import dataclasses
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


def run_forward(
    toml_text: str, *, fidelity: str = "preview", caps: dict = PREVIEW_CAPS
) -> ForwardResult:
    """Run a bounded analytic-backend DFXM forward simulation and return a PNG.

    Validates config, enforces preview caps, forces analytic backend, and renders
    the max-projected detector image as a PNG.

    Args:
        toml_text: TOML configuration string (empty string uses library defaults).
        fidelity: Only "preview" is implemented; "mc" raises NotImplementedError.
        caps: Cap dict with keys max_npixels, max_nsub, max_frames.

    Returns:
        ForwardResult with png_bytes, stats, and bounded=True.

    Raises:
        ValueError: If config is invalid, or user explicitly set a parameter over cap.
        NotImplementedError: If fidelity != "preview".
    """
    # --- Validation first ---
    report = validate_config(toml_text)
    if not report.ok:
        raise ValueError(report.issues[0].problem)

    # --- Fidelity guard ---
    if fidelity != "preview":
        raise NotImplementedError("MC fidelity is added in Phase D (Task 12).")

    # --- Check for explicitly over-cap Npixels in raw TOML ---
    # Empty TOML or omitted detector_geometry gets clamped silently.
    # User-specified Npixels that exceeds the cap is refused with a clear message.
    raw = tomllib.loads(toml_text)
    user_npixels = raw.get("detector_geometry", {}).get("Npixels")
    if user_npixels is not None and int(user_npixels) > caps["max_npixels"]:
        raise ValueError(
            f"Npixels={user_npixels} exceeds the preview cap "
            f"({caps['max_npixels']}). Run production sizes with the dfxm-forward CLI."
        )
    user_nsub = raw.get("detector_geometry", {}).get("Nsub")
    if user_nsub is not None and int(user_nsub) > caps["max_nsub"]:
        raise ValueError(
            f"Nsub={user_nsub} exceeds the preview cap "
            f"({caps['max_nsub']}). Use the dfxm-forward CLI."
        )

    with tempfile.TemporaryDirectory() as d:
        cfg_path = Path(d) / "config.toml"
        cfg_path.write_text(toml_text, encoding="utf-8")
        config = SimulationConfig.from_toml(cfg_path)

        # Cap Npixels and Nsub to preview limits (handles library defaults > cap).
        if config.detector_geometry.Npixels > caps["max_npixels"]:
            config.detector_geometry = dataclasses.replace(
                config.detector_geometry, Npixels=caps["max_npixels"]
            )
        if config.detector_geometry.Nsub > caps["max_nsub"]:
            config.detector_geometry = dataclasses.replace(
                config.detector_geometry, Nsub=caps["max_nsub"]
            )

        # Check frame count.
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
            frames = np.asarray(h5[_IMAGE_DATASET])  # (frames, H, W) or (H, W)

    image = frames.max(axis=0) if frames.ndim == 3 else frames
    stats: ForwardStats = {
        "shape": tuple(int(s) for s in image.shape),
        "vmin": float(image.min()),
        "vmax": float(image.max()),
        "backend": "analytic",
        "kernel": None,
        "wall_s": round(wall_s, 3),
    }
    return ForwardResult(png_bytes=_render_png(image), stats=stats, bounded=True)
