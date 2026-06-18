"""Anisotropic pixel aspect.

DFXM detector x-pixels are coarser than y-pixels by ~1/sin(2theta) (≈3.24 for
Al (111) at 17 keV), so the simulated image has fewer columns than rows for a
square field of view. The preview must stretch x by that factor at render time
(imshow aspect = sin(2theta)) so it shows the physical square, not a tall strip.
"""

from __future__ import annotations

import math
import pathlib
import struct
import tempfile

import numpy as np
import pytest

from dfxm_geo_mcp.ops.forward import _pixel_aspect, _render_png


def _png_size(b: bytes) -> tuple[int, int]:
    # PNG IHDR: width = bytes 16-19, height = bytes 20-23 (big-endian uint32).
    w, h = struct.unpack(">II", b[16:24])
    return w, h


def test_render_png_accepts_aspect_and_returns_valid_png():
    img = np.random.default_rng(0).random((32, 32))
    png = _render_png(img, aspect=0.3)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_png_aspect_below_one_widens_the_image():
    # 100 rows (y) x 30 cols (x): with square pixels this renders as a tall strip.
    tall = np.random.default_rng(1).random((100, 30))
    square_px = _render_png(tall, aspect=1.0)
    stretched = _render_png(tall, aspect=0.3)  # x-pixels ~3.3x wider
    w0, h0 = _png_size(square_px)
    w1, h1 = _png_size(stretched)
    assert w1 / h1 > w0 / h0  # aspect < 1 stretches x -> wider figure


def test_pixel_aspect_is_sin_two_theta_below_one():
    tt = 0.3127  # ~2*theta_Bragg for Al (111) @ 17 keV, radians
    a = _pixel_aspect(tt)
    assert a == pytest.approx(math.sin(tt))
    assert 0.0 < a < 1.0  # < 1 so imshow widens x


def test_default_config_x_stretch_matches_al111_17kev_anisotropy():
    from dfxm_geo.config import SimulationConfig, run_theta

    from dfxm_geo_mcp.ops.scaffold import scaffold_config

    toml = scaffold_config()  # default: Al (111)-family, 17 keV, weak beam
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "c.toml"
        p.write_text(toml, encoding="utf-8")
        config = SimulationConfig.from_toml(p)
    aspect = _pixel_aspect(2.0 * run_theta(config))
    # x-pixels ~3.24x coarser -> stretch factor ~3.24
    assert 3.0 < 1.0 / aspect < 3.5
