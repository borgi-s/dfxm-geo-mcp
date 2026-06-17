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
def guard_stdout():  # type: ignore[return]
    """Redirect stdout to stderr so library prints can't corrupt stdio JSON-RPC."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def prewarm_jit() -> None:
    """Compile the numba forward + Hg kernels once via a tiny analytic forward."""
    from dfxm_geo_mcp.ops.forward import run_forward

    with guard_stdout():
        run_forward("[detector_geometry]\nNpixels = 16\n")
