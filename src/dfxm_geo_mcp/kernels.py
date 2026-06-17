"""MC kernel cache discovery + on-demand bootstrap driver.

Kernel file-naming convention (simplified mode, verified against
dfxm_geo/reciprocal_space/kernel.py _build_kernel_filename line 302):

    Resq_i_h{h}_k{k}_l{l}_{keV:g}keV_{date}.npz

The :g format drops trailing zeros: 17.0 -> "17", 17.5 -> "17.5".

Kernels live in runtime.cache_dir() / "kernels" (Task 7 also points
dfxm_geo.direct_space.forward_model.pkl_fpath there via point_kernel_lookup_at_cache).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from dfxm_geo_mcp import runtime

# Command prefix for the kernel-build child process. The json spec is appended
# per call. Module-level so tests can point it at a stub (see test_kernels_bootstrap).
_WORKER_CMD = [sys.executable, "-m", "dfxm_geo_mcp._kernel_worker"]


def _kernels_dir() -> Path:
    return runtime.cache_dir() / "kernels"


def _glob_for(hkl: tuple[int, int, int], keV: float) -> str:
    """Return a glob matching any cached kernel for (hkl, keV) in simplified mode.

    Uses :g format for keV to match the real naming convention
    (e.g. 17.0 -> "17", 17.5 -> "17.5").
    """
    return f"Resq_i_h{hkl[0]}_k{hkl[1]}_l{hkl[2]}_{keV:g}keV_*.npz"


def kernel_present(hkl: tuple[int, int, int], keV: float) -> bool:
    """Return True if a cached kernel exists for the given (hkl, keV)."""
    kdir = _kernels_dir()
    if not kdir.exists():
        return False
    return any(kdir.glob(_glob_for(hkl, keV)))


def cached_kernel_names() -> list[str]:
    """Return sorted list of stems of all cached kernel npz files."""
    kdir = _kernels_dir()
    if not kdir.exists():
        return []
    return sorted(p.stem for p in kdir.glob("Resq_i_*.npz"))


def _run_kernel_worker(spec: dict) -> None:
    """Run the kernel build (``_kernel_worker``) in a child process.

    Isolation is the whole point: the child's (very chatty) stdout is discarded
    so it can never corrupt the server's JSON-RPC channel, and its stdin is
    pinned to DEVNULL so it can't inherit the server's JSON-RPC stdin pipe (the
    same inherited-handle hazard that hung run_forward). stderr is captured for
    diagnostics. Raises RuntimeError on a non-zero exit.
    """
    proc = subprocess.run(
        [*_WORKER_CMD, json.dumps(spec)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(
            f"kernel bootstrap subprocess failed (exit {proc.returncode}):\n{tail}"
        )


def bootstrap(
    hkl: tuple[int, int, int],
    keV: float,
    *,
    mount_toml: str | None,
    report: Callable[[float, str], None],
) -> str:
    """Build an MC kernel for (hkl, keV) into the cache; return its path.

    The Monte Carlo build runs in a child process (see :func:`_run_kernel_worker`)
    so its stdout chatter cannot corrupt the stdio server's JSON-RPC channel.

    Args:
        hkl: Miller indices of the reflection.
        keV: beam energy in keV.
        mount_toml: TOML string containing a [crystal] block, or None for the
            default Al crystal.
        report: progress callback from the Task 10 job registry,
            signature report(progress: float, message: str).

    Returns:
        Absolute path string of the written kernel npz.

    Raises:
        RuntimeError: if the child process fails, or finishes without writing
            the kernel.
    """
    report(0.0, "starting kernel bootstrap")

    # Build output filename using the real naming convention (:g for keV). The
    # child re-derives the crystal mount from mount_toml and writes here.
    date = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"Resq_i_h{hkl[0]}_k{hkl[1]}_l{hkl[2]}_{keV:g}keV_{date}.npz"
    out = _kernels_dir() / filename
    out.parent.mkdir(parents=True, exist_ok=True)

    report(0.1, f"running Monte Carlo kernel generation -> {out.name}")
    _run_kernel_worker(
        {
            "hkl": list(hkl),
            "keV": keV,
            "mount_toml": mount_toml,
            "output_path": str(out),
            "date": date,
        }
    )
    if not out.exists():
        raise RuntimeError(
            f"kernel bootstrap subprocess exited cleanly but {out.name} was not written"
        )

    report(1.0, f"kernel built at {out}")
    return str(out)
