"""Tests for server helpers and MCP resources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client

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


def test_read_file_returns_text(populated_data_dir: Path) -> None:
    content = server.read_file("hello.txt")
    assert content == "Hello from test\nsecond line\n"


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

    assert {"grep", "pdfgrep"} <= names


async def test_read_file_via_mcp_client() -> None:
    async with Client(server.mcp) as client:
        result = await client.read_resource("data://files/hello.txt")

    assert "resources-mcp" in result[0].text


@pytest.mark.usefixtures("require_rg")
async def test_server_grep_tool_integration() -> None:
    output = await call_tool(server.mcp, "grep", {"pattern": "resources-mcp"})
    assert "hello.txt" in output
    assert "resources-mcp" in output
