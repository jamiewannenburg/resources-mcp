"""Tests for server helpers and MCP resources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

import server
from tests.conftest import call_tool


def test_guess_mime() -> None:
    assert server._guess_mime(Path("readme.txt")) == "text/plain"
    assert server._guess_mime(Path("data.json")) == "application/json"
    assert server._guess_mime(Path("blob.bin")) == "application/octet-stream"


def test_is_text_mime() -> None:
    assert server._is_text_mime("text/plain") is True
    assert server._is_text_mime("application/json") is True
    assert server._is_text_mime("application/octet-stream") is False


def test_safe_resolve_accepts_relative_path(data_dir: Path) -> None:
    target = data_dir / "hello.txt"
    target.write_text("hi", encoding="utf-8")

    resolved = server._safe_resolve("hello.txt")
    assert resolved == target


def test_safe_resolve_rejects_traversal(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="Path traversal is not allowed"):
        server._safe_resolve("../outside.txt")


def test_iter_files_recursive(populated_data_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "RECURSIVE", True)

    files = server._iter_files()
    rel_paths = {path.relative_to(populated_data_dir).as_posix() for path in files}

    assert rel_paths == {"hello.txt", "subdir/nested.json", "sample.pdf"}


def test_iter_files_non_recursive(populated_data_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "RECURSIVE", False)

    files = server._iter_files()
    rel_paths = {path.relative_to(populated_data_dir).as_posix() for path in files}

    assert rel_paths == {"hello.txt", "sample.pdf"}


def test_file_entries(populated_data_dir: Path) -> None:
    entries = server._file_entries()
    paths = {entry["path"] for entry in entries}

    assert "hello.txt" in paths
    assert "subdir/nested.json" in paths
    assert all(isinstance(entry["size"], int) for entry in entries)


def test_data_directory_listing(populated_data_dir: Path) -> None:
    payload = json.loads(server.data_directory_listing())
    paths = {entry["path"] for entry in payload["files"]}

    assert "hello.txt" in paths
    assert "subdir/nested.json" in paths


async def test_mcp_resource_contract() -> None:
    resources = await server.mcp.list_resources()
    resources_by_uri = {str(resource.uri): resource for resource in resources}

    listing = resources_by_uri["resource://data"]
    assert listing.name == "Data directory listing"
    assert listing.mime_type == "application/json"

    templates = await server.mcp.list_resource_templates()
    templates_by_uri = {template.uri_template: template for template in templates}

    file_template = templates_by_uri["data://files/{filepath*}"]
    assert file_template.name == "read_file"
    assert file_template.parameters["required"] == ["filepath"]
    assert file_template.parameters["properties"]["filepath"]["type"] == "string"


async def test_registered_file_resources_include_size(
    populated_data_dir: Path,
    monkeypatch,
) -> None:
    file_mcp = FastMCP("file-resource-test")
    monkeypatch.setattr(server, "mcp", file_mcp)

    count = server.register_file_resources()

    assert count == 3
    resources = await file_mcp.list_resources()
    resources_by_uri = {str(resource.uri): resource for resource in resources}

    hello = resources_by_uri["data://files/hello.txt"]
    assert hello.name == "hello.txt"
    assert hello.mime_type == "text/plain"
    assert hello.size == (populated_data_dir / "hello.txt").stat().st_size

    nested = resources_by_uri["data://files/subdir/nested.json"]
    assert nested.mime_type == "application/json"
    assert nested.size == (populated_data_dir / "subdir" / "nested.json").stat().st_size


def test_read_file_returns_text(populated_data_dir: Path) -> None:
    content = server.read_file("hello.txt")
    assert content == "Hello from test\nsecond line\n"


def test_read_file_returns_bytes_for_binary(data_dir: Path) -> None:
    (data_dir / "blob.bin").write_bytes(b"\x00\x01\x02")

    content = server.read_file("blob.bin")

    assert content == b"\x00\x01\x02"


def test_read_file_missing_file_raises(populated_data_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="File not found"):
        server.read_file("missing.txt")


def test_sized_file_resource_includes_size(tmp_path: Path) -> None:
    file_path = tmp_path / "hello.txt"
    file_path.write_text("hi", encoding="utf-8")

    resource = server.SizedFileResource(
        uri="data://files/hello.txt",
        path=file_path,
        name="hello.txt",
        description="test",
        mime_type="text/plain",
        size=42,
    )
    mcp_resource = resource.to_mcp_resource()

    assert mcp_resource.size == 42


async def test_server_exposes_search_tools() -> None:
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}

    if server.NAMESPACE:
        prefix = f"{server.NAMESPACE}_"
        assert {f"{prefix}grep", f"{prefix}pdfgrep"} <= names
    else:
        assert {"grep", "pdfgrep"} <= names


async def test_mcp_tool_contracts() -> None:
    tools = await server.mcp.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    prefix = f"{server.NAMESPACE}_" if server.NAMESPACE else ""

    grep = tools_by_name[f"{prefix}grep"]
    assert grep.parameters["required"] == ["pattern"]
    assert grep.parameters["additionalProperties"] is False
    assert grep.parameters["properties"]["output_mode"]["enum"] == [
        "content",
        "files_with_matches",
        "count",
    ]
    assert grep.parameters["properties"]["case_insensitive"]["type"] == "boolean"
    assert grep.output_schema["properties"]["result"]["type"] == "string"

    pdfgrep = tools_by_name[f"{prefix}pdfgrep"]
    assert pdfgrep.parameters["required"] == ["pattern"]
    assert pdfgrep.parameters["additionalProperties"] is False
    assert pdfgrep.parameters["properties"]["recursive"]["default"] is True
    assert pdfgrep.parameters["properties"]["page_numbers"]["default"] is True
    assert pdfgrep.output_schema["properties"]["result"]["type"] == "string"


@pytest.mark.usefixtures("require_rg")
async def test_mount_server_with_namespace() -> None:
    if server.NAMESPACE:
        pytest.skip("server module already applies its own namespace transform")

    from fastmcp import Client, FastMCP

    main = FastMCP("main")
    main.mount(server.mcp, namespace="nas")

    tools = await main.list_tools()
    tool_names = {tool.name for tool in tools}
    assert {"nas_grep", "nas_pdfgrep"} <= tool_names
    assert "grep" not in tool_names
    assert "pdfgrep" not in tool_names

    resources = await main.list_resources()
    uris = {str(resource.uri) for resource in resources}
    assert "resource://nas/data" in uris
    assert any(uri.startswith("data://nas/files/") for uri in uris)

    templates = await main.list_resource_templates()
    assert "data://nas/files/{filepath*}" in {t.uri_template for t in templates}

    async with Client(main) as client:
        listing = await client.read_resource("resource://nas/data")
        assert "hello.txt" in listing[0].text

        file_content = await client.read_resource("data://nas/files/hello.txt")
        assert "resources-mcp" in file_content[0].text

        grep_output = await client.call_tool(
            "nas_grep", {"pattern": "resources-mcp"}
        )
        assert "hello.txt" in grep_output.content[0].text
        assert "resources-mcp" in grep_output.content[0].text


async def test_namespace_prefixes_tools_and_resources(populated_data_dir: Path) -> None:
    from fastmcp import FastMCP
    from fastmcp.server.transforms.namespace import Namespace

    from search_tools import register_search_tools
    from tests.conftest import make_safe_resolve

    mcp = FastMCP("test-namespace", transforms=[Namespace("nas")])
    register_search_tools(mcp, populated_data_dir, make_safe_resolve(populated_data_dir))

    @mcp.resource("resource://data")
    def listing() -> str:
        return "[]"

    tools = await mcp.list_tools()
    assert {tool.name for tool in tools} == {"nas_grep", "nas_pdfgrep"}

    resources = await mcp.list_resources()
    assert {str(resource.uri) for resource in resources} == {"resource://nas/data"}


async def test_read_file_via_mcp_client() -> None:
    async with Client(server.mcp) as client:
        result = await client.read_resource("data://files/hello.txt")

    assert "resources-mcp" in result[0].text


@pytest.mark.usefixtures("require_rg")
async def test_server_grep_tool_integration() -> None:
    output = await call_tool(server.mcp, "grep", {"pattern": "resources-mcp"})
    assert "hello.txt" in output
    assert "resources-mcp" in output
