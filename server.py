"""FastMCP server exposing all files in /data as listable, downloadable MCP resources."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP, settings as fastmcp_settings
from fastmcp.resources import FileResource
from fastmcp.server.transforms.namespace import Namespace
from mcp.types import Resource as SDKResource
from pydantic import Field
from search_tools import register_search_tools
from typing_extensions import override

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data")).resolve()
RECURSIVE = os.environ.get("RECURSIVE", "true").lower() in {"1", "true", "yes"}


def _read_namespace() -> str | None:
    """Read optional namespace from NAMESPACE env or --namespace CLI flag."""
    for index, arg in enumerate(sys.argv):
        if arg in ("--namespace", "-n") and index + 1 < len(sys.argv):
            value = sys.argv[index + 1].strip()
            return value or None
        if arg.startswith("--namespace="):
            value = arg.split("=", 1)[1].strip()
            return value or None

    value = os.environ.get("NAMESPACE", "").strip()
    return value or None


NAMESPACE = _read_namespace()

TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
}

mcp = FastMCP("resources-mcp")


class SizedFileResource(FileResource):
    """FileResource that exposes byte size in resources/list responses."""

    size: int = Field(description="File size in bytes")

    @override
    def to_mcp_resource(self, **overrides: Any) -> SDKResource:
        return super().to_mcp_resource(**overrides).model_copy(
            update={"size": overrides.get("size", self.size)}
        )


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def _is_text_mime(mime: str) -> bool:
    return mime.startswith(TEXT_MIME_PREFIXES) or mime in TEXT_MIME_TYPES


def _safe_resolve(relative_path: str) -> Path:
    """Resolve a path under DATA_DIR, rejecting traversal attempts."""
    target = (DATA_DIR / relative_path).resolve()
    try:
        target.relative_to(DATA_DIR)
    except ValueError as exc:
        raise ValueError("Path traversal is not allowed") from exc
    return target


def _iter_files() -> list[Path]:
    if not DATA_DIR.is_dir():
        return []
    iterator = DATA_DIR.rglob("*") if RECURSIVE else DATA_DIR.glob("*")
    return sorted(path for path in iterator if path.is_file())


def _file_entries() -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    for file_path in _iter_files():
        rel = file_path.relative_to(DATA_DIR).as_posix()
        entries.append({"path": rel, "size": file_path.stat().st_size})
    return entries


@mcp.resource(
    "resource://data",
    name="Data directory listing",
    description="JSON listing of all files in the mounted /data directory.",
    mime_type="application/json",
)
def data_directory_listing() -> str:
    return json.dumps({"files": _file_entries()}, indent=2)


def register_file_resources() -> int:
    """Register each file under DATA_DIR as an MCP resource."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for file_path in _iter_files():
        rel = file_path.relative_to(DATA_DIR).as_posix()
        mcp.add_resource(
            SizedFileResource(
                uri=f"data://files/{rel}",
                path=file_path,
                name=rel,
                description=f"File in /data: {rel}",
                mime_type=_guess_mime(file_path),
                size=file_path.stat().st_size,
            )
        )
        count += 1
    return count


@mcp.resource("data://files/{filepath*}")
def read_file(filepath: str) -> str | bytes:
    """Download a file from /data by its relative path."""
    target = _safe_resolve(filepath)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {filepath}")

    mime = _guess_mime(target)
    if _is_text_mime(mime):
        return target.read_text(encoding="utf-8", errors="replace")
    return target.read_bytes()


register_search_tools(mcp, DATA_DIR, _safe_resolve)

registered_files = register_file_resources()

if NAMESPACE:
    mcp.add_transform(Namespace(NAMESPACE))

_http_transport = fastmcp_settings.transport
if _http_transport not in ("http", "streamable-http", "sse"):
    _http_transport = "streamable-http"

app = mcp.http_app(transport=_http_transport)


if __name__ == "__main__":
    import uvicorn

    namespace_note = f" (namespace: {NAMESPACE})" if NAMESPACE else ""
    print(f"Serving {registered_files} file(s) from {DATA_DIR}{namespace_note}")
    uvicorn.run(
        "server:app",
        host=fastmcp_settings.host,
        port=fastmcp_settings.port,
        log_level=fastmcp_settings.log_level.lower(),
    )
