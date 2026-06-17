"""MC kernel cache discovery + on-demand bootstrap driver.

Kernel file-naming convention (simplified mode, verified against
dfxm_geo/reciprocal_space/kernel.py _build_kernel_filename line 302):

    Resq_i_h{h}_k{k}_l{l}_{keV:g}keV_{date}.npz

The :g format drops trailing zeros: 17.0 -> "17", 17.5 -> "17.5".

Kernels live in runtime.cache_dir() / "kernels" (Task 7 also points
dfxm_geo.direct_space.forward_model.pkl_fpath there via point_kernel_lookup_at_cache).
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Callable

from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml, generate_kernel

from dfxm_geo_mcp import runtime


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


def bootstrap(
    hkl: tuple[int, int, int],
    keV: float,
    *,
    mount_toml: str | None,
    report: Callable[[float, str], None],
) -> str:
    """Build an MC kernel for (hkl, keV) into the cache; return its path.

    Args:
        hkl: Miller indices of the reflection.
        keV: beam energy in keV.
        mount_toml: TOML string containing a [crystal] block, or None for the
            default Al crystal.
        report: progress callback from the Task 10 job registry,
            signature report(progress: float, message: str).

    Returns:
        Absolute path string of the written kernel npz.
    """
    report(0.0, "starting kernel bootstrap")

    # Parse optional crystal mount from TOML [crystal] block.
    data: dict = tomllib.loads(mount_toml) if mount_toml else {}
    mount = _crystal_mount_from_toml(data.get("crystal"))

    report(0.05, "crystal mount resolved")

    # Build output filename using the real naming convention (:g for keV).
    date = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"Resq_i_h{hkl[0]}_k{hkl[1]}_l{hkl[2]}_{keV:g}keV_{date}.npz"
    out = _kernels_dir() / filename

    out.parent.mkdir(parents=True, exist_ok=True)

    report(0.1, f"running Monte Carlo kernel generation -> {out.name}")

    # generate_kernel signature (all keyword-only except date):
    #   generate_kernel(date=None, *, ..., output_path=None, hkl=None, keV=None,
    #                   theta=..., mount=None, mode="simplified", eta=0.0,
    #                   omega=0.0, seed=None, batch_size=None, ...) -> Path
    # We pass output_path explicitly so the file lands in the cache dir.
    # theta is computed internally from hkl/keV by generate_kernel when hkl+keV
    # are provided (it stores them as metadata); we also pass date to fix the name.
    written = generate_kernel(
        date=date,
        output_path=out,
        hkl=hkl,
        keV=keV,
        mount=mount,
    )

    report(1.0, f"kernel built at {written}")
    return str(written)
