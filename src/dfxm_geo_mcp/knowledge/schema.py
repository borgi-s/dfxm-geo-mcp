"""Generated config schema + bundled example configs (MCP resources)."""

from __future__ import annotations

import dataclasses
from importlib.resources import files

from dfxm_geo.config import DetectorGeometryConfig, ReciprocalConfig

_BLOCKS = {"reciprocal": ReciprocalConfig, "detector_geometry": DetectorGeometryConfig}


def config_schema() -> dict[str, dict]:
    schema: dict[str, dict] = {}
    for block, cls in _BLOCKS.items():
        fields: dict[str, dict] = {}
        for f in dataclasses.fields(cls):
            default = f.default if f.default is not dataclasses.MISSING else None
            fields[f.name] = {"type": str(f.type), "default": repr(default)}
        schema[block] = fields
    return schema


def example_names() -> list[str]:
    return sorted(
        p.name[:-5]
        for p in files("dfxm_geo_mcp.knowledge").joinpath("examples").iterdir()
        if p.name.endswith(".toml")
    )


def list_examples() -> dict[str, str]:
    root = files("dfxm_geo_mcp.knowledge").joinpath("examples")
    return {
        name: root.joinpath(f"{name}.toml").read_text(encoding="utf-8")
        for name in example_names()
    }
