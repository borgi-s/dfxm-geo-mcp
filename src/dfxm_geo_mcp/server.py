"""FastMCP adapter: thin registrations over the ops layer."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from typing import Any, cast

from fastmcp import Context, FastMCP
from fastmcp.apps import UI_EXTENSION_ID, AppConfig

from dfxm_geo_mcp import kernels, runtime
from dfxm_geo_mcp.jobs import JobRegistry
from dfxm_geo_mcp.knowledge import schema as _schema
from dfxm_geo_mcp.ops import forward as _forward
from dfxm_geo_mcp.ops import reflections as _reflections
from dfxm_geo_mcp.ops import scaffold as _scaffold
from dfxm_geo_mcp.ops import validate as _validate
from dfxm_geo_mcp.ui import forward_preview as _ui

INSTRUCTIONS = (
    "Drive the dfxm-geo forward model. Typical flow: scaffold_config -> validate_config "
    "-> run_forward (analytic, no kernel needed). A fidelity='mc' forward needs a "
    "bootstrapped kernel for its reflection/energy; if run_forward reports a missing "
    "kernel, call start_bootstrap then poll get_job_status. Previews are capped "
    "(Npixels<=128, <=9 frames); production runs use the dfxm-forward CLI. "
    "run_forward renders the image inline where the client supports MCP Apps "
    "(Claude Desktop, ChatGPT connector) and ALWAYS also saves the PNG to a file "
    "and reports its path; ALWAYS give the user that saved path so they can open "
    "it even if inline rendering fails. Pass run_forward's output_path (a .png in "
    "the user's working folder, e.g. the Cowork files folder) to control where it "
    "is written."
)

mcp = FastMCP(name="dfxm-geo-mcp", instructions=INSTRUCTIONS)

_JOBS = JobRegistry()


@mcp.tool(annotations={"title": "Validate config", "readOnlyHint": True, "idempotentHint": True})
def validate_config(toml_text: str) -> dict:
    """Parse a dfxm-geo TOML config and report structured issues, or the resolved summary."""
    return dataclasses.asdict(_validate.validate_config(toml_text))


@mcp.tool(annotations={"title": "Find reflections", "readOnlyHint": True, "idempotentHint": True})
def find_reflections(toml_text: str, hkl_max: int = 3) -> list[dict]:
    """List Laue-reachable reflections for the config's crystal mount and beam energy."""
    if not 1 <= hkl_max <= 6:
        raise ValueError(f"hkl_max must be between 1 and 6 (got {hkl_max})")
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


@mcp.resource(_ui.FORWARD_PREVIEW_URI, mime_type="text/html;profile=mcp-app")
def forward_preview_view() -> str:
    """HTML view that renders run_forward's PNG inline (MCP Apps / ChatGPT widget)."""
    return _ui.FORWARD_PREVIEW_HTML


@mcp.tool(
    annotations={"title": "Run forward preview", "readOnlyHint": True},
    # No declared output schema: returns image+text content blocks (or a ToolResult)
    # on success and a structured dict only for the needs-bootstrap case.
    output_schema=None,
    app=AppConfig(resource_uri=_ui.FORWARD_PREVIEW_URI),
    # FastMCP emits only the official io.modelcontextprotocol/ui meta; add the
    # ChatGPT Apps SDK alias by hand so the connector also links the template.
    meta={"openai/outputTemplate": _ui.FORWARD_PREVIEW_URI},
)
def run_forward(
    toml_text: str,
    fidelity: str = "preview",
    output_path: str | None = None,
    ctx: Context | None = None,
) -> list | dict:
    """Run a preview-scale forward simulation, save the DFXM image to a file, and
    return it.

    The rendered PNG is ALWAYS written to a file and its path reported. In clients
    that support MCP Apps (Claude Desktop, ChatGPT connector) the image also renders
    inline via a ui:// template; other clients (Cowork, Claude Code) get the saved
    path plus an inline image content block. Pass ``output_path`` to choose where
    the file is written (a ``.png`` suffix is added if missing).

    ALWAYS tell the user the saved file path so they can open the image.

    For fidelity='mc' with no cached kernel, returns a structured needs-bootstrap
    hint instead.
    """
    result = _forward.run_forward(toml_text, fidelity=fidelity)
    if result.needs_bootstrap:
        return {"needs_bootstrap": True, **(result.bootstrap_hint or {})}

    if output_path is not None:
        path = Path(output_path)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
    else:
        path = runtime.cache_dir() / "previews" / "forward_preview.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.png_bytes)

    supports_ui = False
    if ctx is not None:
        try:
            supports_ui = ctx.client_supports_extension(UI_EXTENSION_ID)
        except Exception:
            supports_ui = False

    return _ui.build_forward_result(
        result.png_bytes, cast(dict[str, Any], result.stats), str(path.resolve()), supports_ui=supports_ui
    )


@mcp.tool(
    annotations={
        "title": "Start kernel bootstrap",
        "readOnlyHint": False,
        "idempotentHint": True,
        "destructiveHint": False,
    }
)
def start_bootstrap(
    hkl: list[int], energy_keV: float = 17.0, mount_toml: str | None = None
) -> dict:
    """Build the MC resolution kernel for a reflection/energy (long; returns a job id)."""
    if len(hkl) != 3:
        raise ValueError(f"hkl must have exactly 3 Miller indices, got {len(hkl)}: {hkl}")
    h = (hkl[0], hkl[1], hkl[2])
    job_id = _JOBS.submit(
        ("kernel", h, energy_keV),
        lambda report: kernels.bootstrap(h, energy_keV, mount_toml=mount_toml, report=report),
    )
    return {"job_id": job_id}


@mcp.tool(annotations={"title": "Job status", "readOnlyHint": True})
def get_job_status(job_id: str) -> dict:
    """Poll a bootstrap job's state and progress."""
    try:
        job = _JOBS.status(job_id)
    except KeyError:
        return {"error": f"unknown job_id: {job_id}"}
    return {"state": job.state, "progress": job.progress, "message": job.message}


@mcp.tool(annotations={"title": "Job result", "readOnlyHint": True})
def get_job_result(job_id: str) -> dict:
    """Fetch a finished bootstrap job's result (kernel path) or its error."""
    try:
        job = _JOBS.status(job_id)
    except KeyError:
        return {"error": f"unknown job_id: {job_id}"}
    if job.state == "succeeded":
        return {"kernel": job.result}
    return {"state": job.state, "error": job.error}


@mcp.resource("schema://config")
def schema_resource() -> dict:
    """The annotated dfxm-geo config schema (generated from the dataclasses)."""
    return _schema.config_schema()


@mcp.resource("examples://{name}")
def example_resource(name: str) -> str:
    """A canonical example config by name (see examples list)."""
    examples = _schema.list_examples()
    if name not in examples:
        raise ValueError(f"unknown example '{name}'; available: {sorted(examples)}")
    return examples[name]


@mcp.resource("kernels://cached")
def cached_kernels_resource() -> list[str]:
    """MC kernels currently cached (instantly runnable at fidelity='mc')."""
    return kernels.cached_kernel_names()


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
    # dfxm-geo collects git-SHA provenance on every HDF5 write via a `git`
    # subprocess that doesn't isolate stdin; behind the stdio transport the git
    # child inherits the JSON-RPC stdin pipe and hangs run_forward. Patch it to
    # pin the child's stdin to DEVNULL (provenance preserved). See runtime.py.
    runtime.harden_git_provenance()
    # No background JIT prewarm: a concurrent thread running a forward sim both prints
    # to stdout and globally redirects stdout (via guard_stdout), either of which
    # corrupts the stdio JSON-RPC channel — in particular it swallowed the `initialize`
    # response, causing clients to time out ("Could not attach"). The first run_forward
    # call pays the one-time numba JIT cost instead (and the on-disk numba cache makes
    # subsequent process starts fast).
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
