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
@pytest.mark.slow
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


@pytest.mark.asyncio
async def test_run_forward_mc_without_kernel_returns_needs_bootstrap():
    from dfxm_geo_mcp import kernels

    if kernels.kernel_present((-1, 1, -1), 17.0):
        pytest.skip("kernel already cached; would trigger a real MC run")
    async with Client(mcp) as client:
        result = await client.call_tool("run_forward", {"toml_text": "", "fidelity": "mc"})
    assert result.data["needs_bootstrap"] is True
    assert result.data["hkl"] == [-1, 1, -1]


@pytest.mark.asyncio
async def test_start_bootstrap_rejects_short_hkl():
    async with Client(mcp) as client:
        with pytest.raises(Exception, match="3 Miller"):
            await client.call_tool("start_bootstrap", {"hkl": [1, 1]})


@pytest.mark.asyncio
async def test_get_job_status_unknown_id_returns_error():
    async with Client(mcp) as client:
        result = await client.call_tool("get_job_status", {"job_id": "bogus-id-does-not-exist"})
    assert "error" in result.data
    assert "bogus-id-does-not-exist" in result.data["error"]


@pytest.mark.asyncio
async def test_scaffold_tool_defaults_to_weak_beam():
    async with Client(mcp) as client:
        result = await client.call_tool("scaffold_config", {})
    assert "[scan.phi]" in result.data


@pytest.mark.asyncio
async def test_scaffold_tool_strong_beam_param_omits_scan_block():
    async with Client(mcp) as client:
        result = await client.call_tool("scaffold_config", {"beam": "strong"})
    assert "[scan.phi]" not in result.data
