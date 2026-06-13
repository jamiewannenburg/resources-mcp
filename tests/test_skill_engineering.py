"""pytest-skill-engineering tests for the MCP-facing contract."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_skill_engineering.copilot import CopilotEval
from pytest_skill_engineering.execution import MCPServer, MCPServerProcess, Wait

ROOT = Path(__file__).resolve().parent.parent
STDIO_SERVER_CODE = "import server; server.mcp.run(transport='stdio')"


def _server_env(data_dir: Path) -> dict[str, str]:
    return {
        "DATA_DIR": str(data_dir),
        "RECURSIVE": "true",
    }


def _mcp_server_config(data_dir: Path) -> MCPServer:
    return MCPServer(
        command=[sys.executable, "-c", STDIO_SERVER_CODE],
        cwd=str(ROOT),
        env=_server_env(data_dir),
        wait=Wait.for_tools(["grep", "pdfgrep"]),
    )


def _copilot_mcp_servers(data_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        "resources": {
            "command": sys.executable,
            "args": ["-c", STDIO_SERVER_CODE],
            "cwd": str(ROOT),
            "env": _server_env(data_dir),
        }
    }


async def test_skill_engineering_discovers_mcp_tools(
    populated_data_dir: Path,
) -> None:
    process = MCPServerProcess(_mcp_server_config(populated_data_dir))
    try:
        await process.start()

        tools = process.get_tools()
        assert {"grep", "pdfgrep"} <= set(tools)
        assert "Search file contents under /data" in tools["grep"]["description"]
        assert tools["grep"]["inputSchema"]["required"] == ["pattern"]
        assert tools["grep"]["inputSchema"]["properties"]["output_mode"]["enum"] == [
            "content",
            "files_with_matches",
            "count",
        ]
    finally:
        await process.stop()


async def test_skill_engineering_calls_mcp_tool(
    populated_data_dir: Path,
) -> None:
    process = MCPServerProcess(_mcp_server_config(populated_data_dir))
    try:
        await process.start()

        output = await process.call_tool(
            "grep",
            {"pattern": "Hello", "path": "hello.txt", "output_mode": "content"},
        )

        assert "hello.txt" in output
        assert "Hello from test" in output
    finally:
        await process.stop()


async def test_skill_engineering_discovers_mcp_resources(
    populated_data_dir: Path,
) -> None:
    process = MCPServerProcess(_mcp_server_config(populated_data_dir))
    try:
        await process.start()
        assert process._session is not None

        resources = await process._session.list_resources()
        resource_uris = {str(resource.uri) for resource in resources.resources}
        assert "resource://data" in resource_uris
        assert "data://files/hello.txt" in resource_uris

        templates = await process._session.list_resource_templates()
        template_uris = {template.uriTemplate for template in templates.resourceTemplates}
        assert "data://files/{filepath*}" in template_uris
    finally:
        await process.stop()


async def test_skill_engineering_reads_mcp_resources(
    populated_data_dir: Path,
) -> None:
    process = MCPServerProcess(_mcp_server_config(populated_data_dir))
    try:
        await process.start()
        assert process._session is not None

        listing = await process._session.read_resource("resource://data")
        assert "hello.txt" in listing.contents[0].text
        assert "subdir/nested.json" in listing.contents[0].text

        file_content = await process._session.read_resource("data://files/hello.txt")
        assert "Hello from test" in file_content.contents[0].text
    finally:
        await process.stop()


@pytest.mark.copilot
@pytest.mark.skipif(
    os.environ.get("RUN_SKILL_ENGINEERING") != "1",
    reason="set RUN_SKILL_ENGINEERING=1 to run live Copilot skill-engineering tests",
)
async def test_copilot_can_choose_grep_tool(
    copilot_eval,
    populated_data_dir: Path,
) -> None:
    agent = CopilotEval(
        name="resources-mcp-grep-eval",
        working_directory=str(ROOT),
        mcp_servers=_copilot_mcp_servers(populated_data_dir),
        instructions=(
            "Use the resources MCP server for questions about files under /data. "
            "Prefer the grep MCP tool when the user asks to find text."
        ),
        max_turns=6,
        timeout_s=180,
    )

    result = await copilot_eval(
        agent,
        "Find the exact text 'Hello from test' in the /data files and report the file name.",
    )

    assert result.success, result.error
    assert "hello.txt" in (result.final_response or "")
    assert result.tool_was_called("grep") or result.tool_was_called("resources_grep")


@pytest.mark.copilot
@pytest.mark.skipif(
    os.environ.get("RUN_SKILL_ENGINEERING") != "1",
    reason="set RUN_SKILL_ENGINEERING=1 to run live Copilot skill-engineering tests",
)
async def test_copilot_can_use_mcp_resources(
    copilot_eval,
    populated_data_dir: Path,
) -> None:
    agent = CopilotEval(
        name="resources-mcp-resource-eval",
        working_directory=str(ROOT),
        mcp_servers=_copilot_mcp_servers(populated_data_dir),
        instructions=(
            "Use MCP resources from the resources server when the user asks to inspect "
            "available data files. Do not use shell commands for /data inspection."
        ),
        max_turns=6,
        timeout_s=180,
    )

    result = await copilot_eval(
        agent,
        "Use MCP resources to inspect /data/hello.txt and tell me what it contains.",
    )

    assert result.success, result.error
    assert "Hello from test" in (result.final_response or "")
