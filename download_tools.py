"""Optional MCP tools for private Cloud Storage downloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

MAX_V4_EXPIRATION_SECONDS = 7 * 24 * 60 * 60


def _coerce_ttl_seconds(
    requested_seconds: int | None,
    *,
    default_seconds: int,
) -> int:
    ttl = default_seconds if requested_seconds is None else requested_seconds
    if ttl <= 0:
        raise ValueError("expires_seconds must be greater than 0")
    if ttl > MAX_V4_EXPIRATION_SECONDS:
        raise ValueError("expires_seconds cannot exceed 604800 seconds")
    return ttl


def _storage_client():
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-storage is required to generate signed URLs"
        ) from exc

    return storage.Client()


def _access_token() -> str:
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError("google-auth is required to sign URLs on Cloud Run") from exc

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Could not obtain Google Cloud access token")
    return credentials.token


def register_download_tools(
    mcp: FastMCP,
    data_dir: Path,
    safe_resolve,
    *,
    bucket_name: str | None,
    default_expires_seconds: int = 900,
    service_account_email: str | None = None,
) -> bool:
    """Register Cloud Storage download tools when a bucket is configured."""

    if not bucket_name:
        return False

    bucket_name = bucket_name.strip()
    if not bucket_name:
        return False

    @mcp.tool(
        description=(
            "Create a temporary signed Cloud Storage URL for a file under /data. "
            "The bucket stays private; anyone with the returned URL can download "
            "the file until it expires."
        ),
    )
    def download_link(
        path: str,
        expires_seconds: int | None = None,
        attachment: bool = True,
    ) -> dict[str, Any]:
        """Create a V4 signed URL for a private Cloud Storage object.

        Args:
            path: File path under /data.
            expires_seconds: Link lifetime in seconds. Defaults to server config.
            attachment: Ask browsers to download the file instead of displaying it.
        """
        target = safe_resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        ttl_seconds = _coerce_ttl_seconds(
            expires_seconds,
            default_seconds=default_expires_seconds,
        )
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        object_name = target.relative_to(data_dir).as_posix()

        blob = _storage_client().bucket(bucket_name).blob(object_name)
        response_disposition = None
        if attachment:
            filename = Path(object_name).name.replace('"', "")
            response_disposition = f'attachment; filename="{filename}"'

        signed_url_kwargs: dict[str, Any] = {
            "version": "v4",
            "expiration": timedelta(seconds=ttl_seconds),
            "method": "GET",
            "response_disposition": response_disposition,
        }
        if service_account_email:
            signed_url_kwargs["service_account_email"] = service_account_email
            signed_url_kwargs["access_token"] = _access_token()

        url = blob.generate_signed_url(**signed_url_kwargs)
        return {
            "url": url,
            "method": "GET",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "expires_seconds": ttl_seconds,
            "bucket": bucket_name,
            "object": object_name,
            "path": object_name,
            "content_disposition": response_disposition,
        }

    return True
