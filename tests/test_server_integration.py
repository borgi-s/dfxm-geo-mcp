import pytest
from fastmcp import Client

from dfxm_geo_mcp.server import mcp


@pytest.mark.asyncio
async def test_lists_all_tools():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"validate_config", "find_reflections", "scaffold_config", "run_forward"} <= names


@pytest.mark.asyncio
async def test_validate_config_tool_returns_structured_ok():
    async with Client(mcp) as client:
        result = await client.call_tool("validate_config", {"toml_text": ""})
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_run_forward_returns_an_image():
    async with Client(mcp) as client:
        result = await client.call_tool("run_forward", {"toml_text": ""})
    assert any(getattr(c, "type", None) == "image" for c in result.content)


@pytest.mark.asyncio
async def test_bootstrap_tools_exist():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"start_bootstrap", "get_job_status", "get_job_result"} <= names


@pytest.mark.asyncio
async def test_lists_resources_and_prompts():
    async with Client(mcp) as client:
        resources = await client.list_resources()
        prompts = {p.name for p in await client.list_prompts()}
    assert prompts == {"guided_forward_simulation", "diagnose_config"}
    assert any("schema" in str(r.uri) for r in resources)
