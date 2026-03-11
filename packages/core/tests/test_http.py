"""Tests for the EarthForge HTTP client wrapper."""

from __future__ import annotations

import httpx
import pytest
import respx

from earthforge.core.config import EarthForgeProfile
from earthforge.core.errors import HttpError
from earthforge.core.http import (
    USER_AGENT,
    get_bytes,
    managed_client,
    request,
)


@pytest.fixture()
def profile() -> EarthForgeProfile:
    """A minimal profile for HTTP tests."""
    return EarthForgeProfile(name="test", storage_backend="local")


# ---------------------------------------------------------------------------
# managed_client
# ---------------------------------------------------------------------------


class TestManagedClient:
    """Tests for the managed_client context manager."""

    @respx.mock
    async def test_yields_working_client(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://example.com/test").respond(200, json={"ok": True})
        async with managed_client(profile) as client:
            resp = await client.get("https://example.com/test")
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}
        assert route.called

    @respx.mock
    async def test_sends_user_agent(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://example.com/ua").respond(200)
        async with managed_client(profile) as client:
            await client.get("https://example.com/ua")
        sent_headers = route.calls[0].request.headers
        assert sent_headers["user-agent"] == USER_AGENT

    @respx.mock
    async def test_follows_redirects(self, profile: EarthForgeProfile) -> None:
        respx.get("https://example.com/old").respond(
            301, headers={"Location": "https://example.com/new"}
        )
        respx.get("https://example.com/new").respond(200, text="arrived")
        async with managed_client(profile) as client:
            resp = await client.get("https://example.com/old")
            assert resp.status_code == 200
            assert resp.text == "arrived"


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------


class TestRequest:
    """Tests for the one-off request helper."""

    @respx.mock
    async def test_get_json(self, profile: EarthForgeProfile) -> None:
        respx.get("https://api.example.com/items").respond(200, json=[1, 2, 3])
        resp = await request(profile, "GET", "https://api.example.com/items")
        assert resp.json() == [1, 2, 3]

    @respx.mock
    async def test_post_with_json_body(self, profile: EarthForgeProfile) -> None:
        route = respx.post("https://api.example.com/search").respond(200, json={"count": 5})
        resp = await request(
            profile, "POST", "https://api.example.com/search", json={"bbox": [1, 2, 3, 4]}
        )
        assert resp.json()["count"] == 5
        assert route.calls[0].request.content  # body was sent

    @respx.mock
    async def test_query_params(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://api.example.com/items").respond(200)
        await request(profile, "GET", "https://api.example.com/items", params={"limit": "10"})
        assert "limit=10" in str(route.calls[0].request.url)

    @respx.mock
    async def test_http_error_raises(self, profile: EarthForgeProfile) -> None:
        respx.get("https://api.example.com/missing").respond(404)
        with pytest.raises(HttpError) as exc_info:
            await request(profile, "GET", "https://api.example.com/missing")
        assert exc_info.value.status_code == 404

    @respx.mock
    async def test_server_error_raises(self, profile: EarthForgeProfile) -> None:
        respx.get("https://api.example.com/broken").respond(500)
        with pytest.raises(HttpError) as exc_info:
            await request(profile, "GET", "https://api.example.com/broken")
        assert exc_info.value.status_code == 500

    @respx.mock
    async def test_timeout_raises_http_error(self, profile: EarthForgeProfile) -> None:
        respx.get("https://api.example.com/slow").mock(side_effect=httpx.ReadTimeout("timed out"))
        with pytest.raises(HttpError, match="timed out"):
            await request(profile, "GET", "https://api.example.com/slow")

    @respx.mock
    async def test_connection_error_raises_http_error(self, profile: EarthForgeProfile) -> None:
        respx.get("https://api.example.com/down").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(HttpError, match="Connection failed"):
            await request(profile, "GET", "https://api.example.com/down")


# ---------------------------------------------------------------------------
# get_bytes
# ---------------------------------------------------------------------------


class TestGetBytes:
    """Tests for the byte-fetching helper with range support."""

    @respx.mock
    async def test_full_fetch(self, profile: EarthForgeProfile) -> None:
        respx.get("https://cdn.example.com/file.tif").respond(200, content=b"\x49\x49\x2a\x00")
        data = await get_bytes(profile, "https://cdn.example.com/file.tif")
        assert data == b"\x49\x49\x2a\x00"

    @respx.mock
    async def test_range_request_headers(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://cdn.example.com/file.tif").respond(206, content=b"\x49\x49")
        await get_bytes(profile, "https://cdn.example.com/file.tif", start=0, end=2)
        range_header = route.calls[0].request.headers.get("range")
        assert range_header == "bytes=0-1"

    @respx.mock
    async def test_range_start_only(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://cdn.example.com/file.tif").respond(206, content=b"data")
        await get_bytes(profile, "https://cdn.example.com/file.tif", start=100)
        range_header = route.calls[0].request.headers.get("range")
        assert range_header == "bytes=100-"

    @respx.mock
    async def test_range_end_only(self, profile: EarthForgeProfile) -> None:
        route = respx.get("https://cdn.example.com/file.tif").respond(206, content=b"data")
        await get_bytes(profile, "https://cdn.example.com/file.tif", end=512)
        range_header = route.calls[0].request.headers.get("range")
        assert range_header == "bytes=-511"

    @respx.mock
    async def test_404_raises(self, profile: EarthForgeProfile) -> None:
        respx.get("https://cdn.example.com/missing.tif").respond(404)
        with pytest.raises(HttpError) as exc_info:
            await get_bytes(profile, "https://cdn.example.com/missing.tif")
        assert exc_info.value.status_code == 404
