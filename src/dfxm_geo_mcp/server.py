"""FastMCP adapter: thin registrations over the ops layer."""

from __future__ import annotations

import dataclasses
import threading

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from dfxm_geo_mcp import runtime
from dfxm_geo_mcp.knowledge import schema as _schema
from dfxm_geo_mcp.ops import forward as _forward
from dfxm_geo_mcp.ops import reflections as _reflections
from dfxm_geo_mcp.ops import scaffold as _scaffold
from dfxm_geo_mcp.ops import validate as _validate

INSTRUCTIONS = (
    "Drive the dfxm-geo forward model. Typical flow: scaffold_config -> validate_config "
    "-> run_forward (analytic, no kernel needed). A fidelity='mc' forward needs a "
    "bootstrapped kernel for its reflection/energy; if run_forward reports a missing "
    "kernel, call start_bootstrap then poll get_job_status. Previews are capped "
    "(Npixels<=128, <=9 frames); production runs use the dfxm-forward CLI."
)

mcp = FastMCP(name="dfxm-geo-mcp", instructions=INSTRUCTIONS)


@mcp.tool(annotations={"title": "Validate config", "readOnlyHint": True, "idempotentHint": True})
def validate_config(toml_text: str) -> dict:
    """Parse a dfxm-geo TOML config and report structured issues, or the resolved summary."""
    return dataclasses.asdict(_validate.validate_config(toml_text))


@mcp.tool(annotations={"title": "Find reflections", "readOnlyHint": True, "idempotentHint": True})
def find_reflections(toml_text: str, hkl_max: int = 3) -> list[dict]:
    """List Laue-reachable reflections for the config's crystal mount and beam energy."""
    return [
        dataclasses.asdict(r) for r in _reflections.find_reflections(toml_text, hkl_max=hkl_max)
    ]


@mcp.tool(annotations={"title": "Scaffold config", "readOnlyHint": True, "idempotentHint": True})
def scaffold_config(
    material: str | None = None,
    structure_type: str | None = None,
    reflection: list[int] | None = None,
    energy_keV: float = 17.0,
    geometry_mode: str = "symmetric",
    cif_path: str | None = None,
    scan_mode: str = "single",
) -> str:
    """Return a valid starter dfxm-geo config (TOML text) for the requested crystal/reflection."""
    hkl = tuple(reflection) if reflection else None
    return _scaffold.scaffold_config(
        material=material,
        structure_type=structure_type,
        reflection=hkl,  # type: ignore[arg-type]
        energy_keV=energy_keV,
        geometry_mode=geometry_mode,
        cif_path=cif_path,
        scan_mode=scan_mode,
    )


@mcp.tool(annotations={"title": "Run forward preview", "readOnlyHint": True})
def run_forward(toml_text: str, fidelity: str = "preview") -> Image:
    """Run a preview-scale forward simulation and return the rendered DFXM image."""
    result = _forward.run_forward(toml_text, fidelity=fidelity)
    return Image(data=result.png_bytes, format="png")


@mcp.resource("schema://config")
def schema_resource() -> dict:
    """The annotated dfxm-geo config schema (generated from the dataclasses)."""
    return _schema.config_schema()


@mcp.resource("examples://{name}")
def example_resource(name: str) -> str:
    """A canonical example config by name (see examples list)."""
    return _schema.list_examples()[name]


@mcp.resource("kernels://cached")
def cached_kernels_resource() -> list[str]:
    """MC kernels currently cached (instantly runnable at fidelity='mc')."""
    return []  # populated in Task 12


@mcp.prompt()
def guided_forward_simulation(goal: str) -> str:
    """Guide: scaffold -> validate -> run_forward for the user's stated goal."""
    return (
        f"Help the user run a DFXM forward simulation for: {goal}. "
        "Call scaffold_config, then validate_config on the result, then run_forward."
    )


@mcp.prompt()
def diagnose_config(toml_text: str) -> str:
    """Guide: triage a failing config using validate_config's structured issues."""
    return (
        f"Diagnose this dfxm-geo config and propose fixes:\n\n{toml_text}\n\n"
        "Call validate_config and explain each issue's fix."
    )


def main() -> None:
    runtime.configure_numba_cache()
    runtime.point_kernel_lookup_at_cache()
    threading.Thread(target=runtime.prewarm_jit, daemon=True).start()
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
