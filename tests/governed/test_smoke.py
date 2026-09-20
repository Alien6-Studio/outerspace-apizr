import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate as mcp_generate
from apizr.generators.rest import generate as rest_generate
from apizr.governed.mcp import create_server
from apizr.governed.rest import create_app
from apizr.inspection import inspect_source

pytestmark = pytest.mark.timeout(30)
SOURCE = b"def total(values: list[int], /, *, tax:int=2): return sum(values)+tax\nasync def greet(name:str): return name\n"


def test_governed_smoke(tmp_path):
    inspection = inspect_source(SOURCE, module_name="governed_sample")
    rest = tmp_path / "rest"
    rest_generate(inspection, SOURCE, rest, execution_policy=ExecutionPolicy())
    with TestClient(create_app(rest)) as client:
        result = client.post("/capabilities/total", json={"values": [1, 2]})
        assert result.status_code == 200, result.text
        assert result.json() == 5
    mcp = tmp_path / "mcp"
    mcp_generate(inspection, SOURCE, mcp, execution_policy=ExecutionPolicy())

    async def check():
        async with Client(create_server(mcp)) as client:
            result = await client.call_tool("total", {"values": [1, 2]})
            assert not result.is_error, result
            assert result.structured_content == 5

    anyio.run(check)
