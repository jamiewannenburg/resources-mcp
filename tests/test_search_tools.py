"""Tests for grep and pdfgrep MCP tools."""

from __future__ import annotations

import pytest

from tests.conftest import ToolCaller


@pytest.mark.usefixtures("require_rg")
async def test_grep_content_mode(search_tools: ToolCaller) -> None:
    output = await search_tools("grep", {"pattern": "Hello", "output_mode": "content"})
    assert "Hello from test" in output


@pytest.mark.usefixtures("require_rg")
async def test_grep_files_with_matches(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "grep",
        {"pattern": "Hello", "output_mode": "files_with_matches"},
    )
    assert "hello.txt" in output


@pytest.mark.usefixtures("require_rg")
async def test_grep_count_mode(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "grep",
        {"pattern": "Hello", "output_mode": "count", "path": "hello.txt"},
    )
    assert output.strip() == "1"


@pytest.mark.usefixtures("require_rg")
async def test_grep_glob_filter(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "grep",
        {"pattern": "ok", "glob": "*.json", "output_mode": "content"},
    )
    assert '{"ok": true}' in output
    assert "hello.txt" not in output


@pytest.mark.usefixtures("require_rg")
async def test_grep_case_insensitive(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "grep",
        {"pattern": "hello", "case_insensitive": True, "output_mode": "content"},
    )
    assert "Hello from test" in output


@pytest.mark.usefixtures("require_rg")
async def test_grep_head_limit_and_offset(search_tools: ToolCaller) -> None:
    full = await search_tools(
        "grep",
        {"pattern": ".", "path": "hello.txt", "output_mode": "content"},
    )
    lines = full.splitlines()

    limited = await search_tools(
        "grep",
        {
            "pattern": ".",
            "path": "hello.txt",
            "output_mode": "content",
            "head_limit": 1,
            "offset": 1,
        },
    )
    assert limited == lines[1]


@pytest.mark.usefixtures("require_rg")
async def test_grep_no_matches_returns_empty(search_tools: ToolCaller) -> None:
    output = await search_tools("grep", {"pattern": "does-not-exist-xyz"})
    assert output == ""


@pytest.mark.usefixtures("require_rg")
async def test_grep_missing_path_raises(search_tools: ToolCaller) -> None:
    with pytest.raises(Exception, match="Path not found"):
        await search_tools("grep", {"pattern": "Hello", "path": "missing.txt"})


@pytest.mark.usefixtures("require_rg")
async def test_grep_rejects_path_traversal(search_tools: ToolCaller) -> None:
    with pytest.raises(Exception, match="Path traversal is not allowed"):
        await search_tools("grep", {"pattern": "Hello", "path": "../outside.txt"})


@pytest.mark.usefixtures("require_pdfgrep")
async def test_pdfgrep_content_mode(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "pdfgrep",
        {"pattern": "Searchable", "path": "sample.pdf", "output_mode": "content"},
    )
    assert "Searchable PDF content for tests" in output


@pytest.mark.usefixtures("require_pdfgrep")
async def test_pdfgrep_files_with_matches(search_tools: ToolCaller) -> None:
    output = await search_tools(
        "pdfgrep",
        {"pattern": "Searchable", "output_mode": "files_with_matches"},
    )
    assert "sample.pdf" in output


@pytest.mark.usefixtures("require_pdfgrep")
async def test_pdfgrep_no_matches_returns_empty(search_tools: ToolCaller) -> None:
    output = await search_tools("pdfgrep", {"pattern": "does-not-exist-xyz"})
    assert output == ""


@pytest.mark.usefixtures("require_pdfgrep")
async def test_pdfgrep_missing_path_raises(search_tools: ToolCaller) -> None:
    with pytest.raises(Exception, match="Path not found"):
        await search_tools("pdfgrep", {"pattern": "Searchable", "path": "missing.pdf"})
