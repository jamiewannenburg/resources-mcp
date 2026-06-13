"""Tests for optional Cloud Storage download link tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import FastMCP

import download_tools
from download_tools import register_download_tools
from tests.conftest import call_tool, make_safe_resolve


class FakeBlob:
    def __init__(self, object_name: str) -> None:
        self.object_name = object_name
        self.signed_url_kwargs = None

    def generate_signed_url(self, **kwargs):
        self.signed_url_kwargs = kwargs
        return f"https://storage.googleapis.com/private/{self.object_name}?signed=true"


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, object_name: str) -> FakeBlob:
        blob = FakeBlob(object_name)
        self.blobs[object_name] = blob
        return blob


class FakeClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, bucket_name: str) -> FakeBucket:
        bucket = FakeBucket()
        self.buckets[bucket_name] = bucket
        return bucket


def _payload(text: str) -> dict:
    return json.loads(text)


async def test_download_link_not_registered_without_bucket(populated_data_dir: Path):
    mcp = FastMCP("download-test")
    registered = register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name=None,
    )

    assert registered is False
    assert {tool.name for tool in await mcp.list_tools()} == set()


async def test_download_link_generates_signed_url(
    populated_data_dir: Path,
    monkeypatch,
):
    fake_client = FakeClient()
    monkeypatch.setattr(download_tools, "_storage_client", lambda: fake_client)

    mcp = FastMCP("download-test")
    registered = register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name="private-bucket",
        default_expires_seconds=300,
    )

    assert registered is True
    assert {tool.name for tool in await mcp.list_tools()} == {"download_link"}

    output = await call_tool(mcp, "download_link", {"path": "hello.txt"})
    payload = _payload(output)

    assert payload["url"] == (
        "https://storage.googleapis.com/private/hello.txt?signed=true"
    )
    assert payload["method"] == "GET"
    assert payload["expires_seconds"] == 300
    assert payload["bucket"] == "private-bucket"
    assert payload["object"] == "hello.txt"
    assert payload["path"] == "hello.txt"
    assert payload["content_disposition"] == 'attachment; filename="hello.txt"'

    blob = fake_client.buckets["private-bucket"].blobs["hello.txt"]
    assert blob.signed_url_kwargs["version"] == "v4"
    assert blob.signed_url_kwargs["method"] == "GET"
    assert blob.signed_url_kwargs["response_disposition"] == (
        'attachment; filename="hello.txt"'
    )


async def test_download_link_rejects_path_traversal(populated_data_dir: Path):
    mcp = FastMCP("download-test")
    register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name="private-bucket",
    )

    with pytest.raises(Exception, match="Path traversal is not allowed"):
        await call_tool(mcp, "download_link", {"path": "../secret.txt"})


async def test_download_link_rejects_missing_file(populated_data_dir: Path):
    mcp = FastMCP("download-test")
    register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name="private-bucket",
    )

    with pytest.raises(Exception, match="File not found"):
        await call_tool(mcp, "download_link", {"path": "missing.txt"})


async def test_download_link_rejects_ttl_above_v4_limit(
    populated_data_dir: Path,
    monkeypatch,
):
    monkeypatch.setattr(download_tools, "_storage_client", FakeClient)

    mcp = FastMCP("download-test")
    register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name="private-bucket",
    )

    with pytest.raises(Exception, match="expires_seconds cannot exceed"):
        await call_tool(
            mcp,
            "download_link",
            {"path": "hello.txt", "expires_seconds": 604801},
        )


async def test_download_link_can_sign_with_service_account_email(
    populated_data_dir: Path,
    monkeypatch,
):
    fake_client = FakeClient()
    monkeypatch.setattr(download_tools, "_storage_client", lambda: fake_client)
    monkeypatch.setattr(download_tools, "_access_token", lambda: "access-token")

    mcp = FastMCP("download-test")
    register_download_tools(
        mcp,
        populated_data_dir,
        make_safe_resolve(populated_data_dir),
        bucket_name="private-bucket",
        service_account_email="signer@example.iam.gserviceaccount.com",
    )

    await call_tool(mcp, "download_link", {"path": "hello.txt"})

    blob = fake_client.buckets["private-bucket"].blobs["hello.txt"]
    assert blob.signed_url_kwargs["service_account_email"] == (
        "signer@example.iam.gserviceaccount.com"
    )
    assert blob.signed_url_kwargs["access_token"] == "access-token"

