"""MCP server for the dfxm-geo dark-field X-ray microscopy forward model."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dfxm-geo-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
