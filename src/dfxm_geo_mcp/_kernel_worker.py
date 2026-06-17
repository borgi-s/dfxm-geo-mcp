"""Child-process entry point: build one MC kernel off the JSON-RPC channel.

``dfxm_geo.reciprocal_space.kernel.generate_kernel`` prints ~50s of progress
chatter to stdout. ``start_bootstrap`` runs the build in a ``JobRegistry``
background thread *concurrently* with the stdio server, so that chatter would
land on the server's real stdout — which over the stdio transport carries
JSON-RPC — and corrupt the protocol. A process-global ``redirect_stdout`` from
that concurrent thread is unsafe (it would also swallow the server's own
JSON-RPC writes — the Bug-A failure mode), so the build runs here, in a separate
process whose stdout the parent discards (and whose stdin the parent pins to
DEVNULL so it can never inherit the server's JSON-RPC stdin pipe).

Usage (spawned by ``kernels._run_kernel_worker``)::

    python -m dfxm_geo_mcp._kernel_worker '<json spec>'

where ``spec`` = ``{"hkl": [h, k, l], "keV": float, "mount_toml": str | null,
"output_path": str, "date": str}``. Exit 0 on success; on failure the traceback
goes to stderr (captured by the parent for diagnostics) and the process exits 1.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


def run(spec: dict) -> Path:
    """Build the kernel described by ``spec`` and return the written npz path."""
    from dfxm_geo.reciprocal_space.kernel import _crystal_mount_from_toml, generate_kernel

    from dfxm_geo_mcp import runtime

    # Same cache/kernel-lookup wiring as the server, so the child's numba JIT
    # cache is shared and the npz lands where the server discovers it.
    runtime.configure_numba_cache()
    runtime.point_kernel_lookup_at_cache()

    data: dict = tomllib.loads(spec["mount_toml"]) if spec["mount_toml"] else {}
    mount = _crystal_mount_from_toml(data.get("crystal"))
    out = Path(spec["output_path"])
    out.parent.mkdir(parents=True, exist_ok=True)

    return generate_kernel(
        date=spec["date"],
        output_path=out,
        hkl=tuple(spec["hkl"]),
        keV=spec["keV"],
        mount=mount,
    )


def main(argv: list[str]) -> int:
    run(json.loads(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
