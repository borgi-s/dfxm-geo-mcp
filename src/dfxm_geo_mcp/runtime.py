"""Startup wiring: cache dirs, kernel-lookup path, stdout guard, JIT pre-warm."""

from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path

from platformdirs import user_cache_dir

_APP = "dfxm-geo-mcp"


def cache_dir() -> Path:
    d = Path(user_cache_dir(_APP))
    (d / "kernels").mkdir(parents=True, exist_ok=True)
    return d


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
        # ``default`` is already a native Path; enforce suffix and return.
        path = default
        if path.suffix.lower() != suffix:
            stem = path.name[: -len(path.suffix)] if path.suffix else path.name
            path = path.parent / (stem + suffix)
        return path

    if (
        os.name == "nt"
        and output_path.startswith("/")
        and re.match(r"^[A-Za-z]:", output_path) is None
        and "\\" not in output_path
    ):
        # POSIX-absolute on Windows: remap basename into cache previews dir.
        # Use string split to avoid PosixPath instantiation on Windows.
        basename = output_path.rstrip("/").rsplit("/", 1)[-1]
        path = cache_dir() / "previews" / basename
        if path.suffix.lower() != suffix:
            stem = path.name[: -len(path.suffix)] if path.suffix else path.name
            path = path.parent / (stem + suffix)
        return path

    # General case: stay in string-land for suffix enforcement to avoid
    # PosixPath/WindowsPath cross-platform issues when os.name is monkeypatched.
    p_str = output_path.replace("\\", "/")
    # Extract the part after the last "/".
    basename = p_str.rstrip("/").rsplit("/", 1)[-1] if "/" in p_str else p_str
    # Directory is everything before the last "/".
    if "/" in p_str.rstrip("/"):
        dirpart = p_str.rstrip("/").rsplit("/", 1)[0]
    else:
        dirpart = ""
    # Enforce suffix on basename.
    dot_idx = basename.rfind(".")
    if dot_idx == -1:
        basename_fixed = basename + suffix
    elif basename[dot_idx:].lower() != suffix:
        basename_fixed = basename[:dot_idx] + suffix
    else:
        basename_fixed = basename
    # Reconstruct and convert to Path.
    if dirpart:
        return Path(dirpart + "/" + basename_fixed)
    return Path(basename_fixed)


def configure_numba_cache() -> None:
    nb = cache_dir() / "numba"
    nb.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(nb)


def point_kernel_lookup_at_cache() -> None:
    import dfxm_geo.direct_space.forward_model as fm

    fm.pkl_fpath = str(cache_dir() / "kernels")


def harden_git_provenance() -> None:
    """Make dfxm-geo's git-SHA provenance collection safe behind the stdio server.

    On every HDF5 write dfxm-geo records ``(git_sha, git_dirty)`` via
    ``dfxm_geo.io.hdf5._get_git_sha_and_dirty``, which shells out to ``git`` with
    ``subprocess.check_output`` WITHOUT isolating the child's stdin. Under the
    stdio MCP transport the server's stdin is the live JSON-RPC pipe; the spawned
    ``git`` inherits that handle and ``communicate()`` blocks forever, hanging the
    very first ``run_forward`` (the standalone controls never saw it because their
    stdin is an inert console handle, not a held-open pipe).

    Replace the collector with a byte-for-byte equivalent that pins the git
    child's stdin to ``DEVNULL`` — provenance is preserved; only the inherited
    pipe handle is removed. Idempotent; safe to call once at startup. No-op if the
    library symbol is absent (a future dfxm-geo refactor) — the stdio smoke test
    (``tests/test_server_stdio.py``) guards against a silent regression.
    """
    import subprocess

    try:
        import dfxm_geo.io.hdf5 as _hdf5
    except Exception:
        return
    if not hasattr(_hdf5, "_get_git_sha_and_dirty"):
        return

    def _stdin_isolated_git_sha_and_dirty() -> tuple[str, bool]:
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    stdin=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
            )
            return sha, dirty
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown", False

    _hdf5._get_git_sha_and_dirty = _stdin_isolated_git_sha_and_dirty


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
