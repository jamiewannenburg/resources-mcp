"""MCP search tools backed by ripgrep (rg) and pdfgrep."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

OutputMode = Literal["content", "files_with_matches", "count"]


def register_search_tools(mcp: FastMCP, data_dir: Path, safe_resolve) -> None:
    """Register grep and pdfgrep tools constrained to paths under data_dir."""

    def _resolve_search_target(relative_path: str | None) -> Path:
        if relative_path is None or relative_path.strip() == "":
            return data_dir
        return safe_resolve(relative_path)

    def _search_path_arg(target: Path) -> str:
        if target == data_dir:
            return "."
        return target.relative_to(data_dir).as_posix()

    def _limit_output(
        output: str,
        *,
        head_limit: int | None,
        offset: int | None,
    ) -> str:
        if head_limit is None and offset is None:
            return output

        lines = output.splitlines()
        start = offset or 0
        end = start + head_limit if head_limit is not None else None
        limited = lines[start:end]
        return "\n".join(limited)

    @mcp.tool(
        description=(
            "Search file contents under /data with ripgrep (rg). "
            "Supports regex patterns, glob filters, context lines, output modes, "
            "and pagination via head_limit/offset."
        ),
    )
    def grep(
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        output_mode: OutputMode = "content",
        context_after: int | None = None,
        context_before: int | None = None,
        context: int | None = None,
        case_insensitive: bool = False,
        type: str | None = None,
        head_limit: int | None = None,
        offset: int | None = None,
        multiline: bool = False,
    ) -> str:
        """Search files with ripgrep.

        Args:
            pattern: Regular expression to search for.
            path: File or directory under /data (default: entire /data tree).
            glob: Glob filter passed to rg --glob (e.g. \"*.py\", \"**/*.json\").
            output_mode: \"content\" (matching lines), \"files_with_matches\", or \"count\".
            context_after: Lines of trailing context per match (rg -A).
            context_before: Lines of leading context per match (rg -B).
            context: Lines of context on both sides per match (rg -C).
            case_insensitive: Case-insensitive search (rg -i).
            type: File type filter (rg --type), e.g. \"py\", \"json\".
            head_limit: Maximum number of output lines to return.
            offset: Number of output lines to skip before returning results.
            multiline: Enable multiline matching (rg -U --multiline-dotall).
        """
        target = _resolve_search_target(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {path or '/'}")

        cmd = ["rg", "--regexp", pattern, "--color", "never"]
        if output_mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif output_mode == "count":
            cmd.append("--count")
        else:
            cmd.extend(["--line-number", "--with-filename", "--no-heading"])

        if glob:
            cmd.extend(["--glob", glob])
        if context is not None:
            cmd.extend(["--context", str(context)])
        else:
            if context_after is not None:
                cmd.extend(["--after-context", str(context_after)])
            if context_before is not None:
                cmd.extend(["--before-context", str(context_before)])
        if case_insensitive:
            cmd.append("--ignore-case")
        if type:
            cmd.extend(["--type", type])
        if multiline:
            cmd.extend(["-U", "--multiline-dotall"])

        cmd.append(_search_path_arg(target))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=data_dir,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Required binary not found: rg") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Search timed out: {' '.join(cmd)}") from exc

        if result.returncode > 1:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(detail or f"rg failed with exit code {result.returncode}")

        return _limit_output(result.stdout, head_limit=head_limit, offset=offset)

    @mcp.tool(
        description=(
            "Search PDF files under /data with pdfgrep. "
            "Supports regex patterns, recursive directory search, output modes, "
            "and pagination via head_limit/offset."
        ),
    )
    def pdfgrep(
        pattern: str,
        path: str | None = None,
        output_mode: OutputMode = "content",
        case_insensitive: bool = False,
        page_numbers: bool = True,
        head_limit: int | None = None,
        offset: int | None = None,
        recursive: bool = True,
    ) -> str:
        """Search PDF files with pdfgrep.

        Args:
            pattern: Regular expression to search for.
            path: PDF file or directory under /data (default: entire /data tree).
            output_mode: \"content\" (matching lines), \"files_with_matches\", or \"count\".
            case_insensitive: Case-insensitive search (pdfgrep -i).
            page_numbers: Include page numbers in content output (pdfgrep -n).
            head_limit: Maximum number of output lines to return.
            offset: Number of output lines to skip before returning results.
            recursive: Search directories recursively when path is a directory.
        """
        target = _resolve_search_target(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {path or '/'}")

        cmd = ["pdfgrep", "--color", "never"]
        if output_mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif output_mode == "count":
            cmd.append("--count")
        elif page_numbers:
            cmd.append("--page-number")

        if case_insensitive:
            cmd.append("--ignore-case")
        if target.is_dir() and recursive:
            cmd.append("--recursive")

        cmd.extend(["--regexp", pattern, _search_path_arg(target)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=data_dir,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Required binary not found: pdfgrep") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Search timed out: {' '.join(cmd)}") from exc

        if result.returncode > 1:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                detail or f"pdfgrep failed with exit code {result.returncode}"
            )

        return _limit_output(result.stdout, head_limit=head_limit, offset=offset)
