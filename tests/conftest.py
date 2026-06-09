"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

import server  # noqa: E402

from search_tools import register_search_tools  # noqa: E402

ToolCaller = Callable[[str, dict], Awaitable[str]]


def make_safe_resolve(data_dir: Path):
    def _safe_resolve(relative_path: str) -> Path:
        target = (data_dir / relative_path).resolve()
        try:
            target.relative_to(data_dir)
        except ValueError as exc:
            raise ValueError("Path traversal is not allowed") from exc
        return target

    return _safe_resolve


async def call_tool(mcp: FastMCP, name: str, arguments: dict) -> str:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        return result.content[0].text


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def populated_data_dir(data_dir: Path) -> Path:
    (data_dir / "hello.txt").write_text(
        "Hello from test\nsecond line\n",
        encoding="utf-8",
    )
    nested = data_dir / "subdir"
    nested.mkdir()
    (nested / "nested.json").write_text('{"ok": true}\n', encoding="utf-8")

    pdf_src = Path(__file__).parent / "fixtures" / "searchable.pdf"
    if pdf_src.exists():
        shutil.copy(pdf_src, data_dir / "sample.pdf")

    return data_dir


@pytest.fixture
def search_mcp(populated_data_dir: Path) -> FastMCP:
    mcp = FastMCP("test-search")
    register_search_tools(mcp, populated_data_dir, make_safe_resolve(populated_data_dir))
    return mcp


@pytest.fixture
async def search_tools(search_mcp: FastMCP) -> ToolCaller:
    async def _call(name: str, arguments: dict) -> str:
        return await call_tool(search_mcp, name, arguments)

    return _call


@pytest.fixture(scope="session")
def require_rg() -> None:
    if shutil.which("rg") is None:
        pytest.skip("rg is not installed")


@pytest.fixture(scope="session")
def require_pdfgrep() -> None:
    if shutil.which("pdfgrep") is None:
        pytest.skip("pdfgrep is not installed")
