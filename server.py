"""FastMCP server exposing all files in /data as listable, downloadable MCP resources."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.resources import DirectoryResource, FileResource

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data")).resolve()
RECURSIVE = os.environ.get("RECURSIVE", "true").lower() in {"1", "true", "yes"}
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")

TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
}

mcp = FastMCP("resources-mcp")


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


def register_file_resources() -> int:
    """Register each file under DATA_DIR as an MCP resource."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    listing = DirectoryResource(
        uri="resource://data",
        path=DATA_DIR,
        name="Data directory listing",
        description="JSON listing of all files in the mounted /data directory.",
        recursive=RECURSIVE,
    )
    mcp.add_resource(listing)

    count = 0
    for file_path in _iter_files():
        rel = file_path.relative_to(DATA_DIR).as_posix()
        mcp.add_resource(
            FileResource(
                uri=f"data://files/{rel}",
                path=file_path,
                name=rel,
                description=f"File in /data: {rel}",
                mime_type=_guess_mime(file_path),
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


registered_files = register_file_resources()


if __name__ == "__main__":
    print(f"Serving {registered_files} file(s) from {DATA_DIR}")
    mcp.run(transport=TRANSPORT, host=HOST, port=PORT)
