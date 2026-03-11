"""TerraForge HTTP client wrapper.

All HTTP traffic in TerraForge flows through this module. Domain packages never
import ``httpx`` directly — they call :func:`get_client` to obtain a configured
``httpx.AsyncClient`` with consistent timeouts, retries, and user-agent headers.

The module manages a per-profile client cache so that multiple calls within the
same ``async with`` session reuse connections. Callers should use the client as
a context manager via :func:`managed_client` for automatic cleanup, or manage
the lifecycle manually with :func:`get_client` / :func:`close_client`.

Usage in domain code::

    from terraforge.core.http import managed_client

    async def fetch_stac_item(profile: TerraForgeProfile, url: str) -> dict:
        async with managed_client(profile) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx

from terraforge.core import __version__
from terraforge.core.errors import HttpError

if TYPE_CHECKING:
    from terraforge.core.config import TerraForgeProfile

logger = logging.getLogger(__name__)

#: Default timeout for all HTTP operations (connect, read, write, pool).
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

#: Maximum number of automatic retries on transient failures.
MAX_RETRIES = 3

#: HTTP status codes that trigger an automatic retry.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

#: User-Agent string sent with every request.
USER_AGENT = f"terraforge/{__version__}"


def _build_client(profile: TerraForgeProfile) -> httpx.AsyncClient:
    """Create a new ``httpx.AsyncClient`` configured for the given profile.

    Parameters:
        profile: The active TerraForge profile (used for future auth header injection).

    Returns:
        A configured but not-yet-entered async HTTP client.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    transport = httpx.AsyncHTTPTransport(retries=MAX_RETRIES)

    return httpx.AsyncClient(
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
        transport=transport,
        follow_redirects=True,
    )


@asynccontextmanager
async def managed_client(profile: TerraForgeProfile) -> AsyncIterator[httpx.AsyncClient]:
    """Context manager that provides a configured HTTP client with automatic cleanup.

    This is the preferred way to obtain an HTTP client in domain code. The client
    is created on entry and closed on exit, ensuring connections are released.

    Parameters:
        profile: The active TerraForge profile.

    Yields:
        A configured ``httpx.AsyncClient``.

    Example::

        async with managed_client(profile) as client:
            resp = await client.get("https://example.com")
    """
    client = _build_client(profile)
    try:
        async with client:
            yield client
    except httpx.HTTPStatusError as exc:
        raise HttpError(
            f"HTTP {exc.response.status_code} from {exc.request.url}",
            status_code=exc.response.status_code,
        ) from exc
    except httpx.TimeoutException as exc:
        raise HttpError(f"Request timed out: {exc}") from exc
    except httpx.ConnectError as exc:
        raise HttpError(f"Connection failed: {exc}") from exc


async def request(
    profile: TerraForgeProfile,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    json: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Issue a single HTTP request with TerraForge's standard configuration.

    This is a convenience function for one-off requests. For multiple requests
    within the same operation, prefer :func:`managed_client` to reuse connections.

    Parameters:
        profile: The active TerraForge profile.
        method: HTTP method (``"GET"``, ``"POST"``, etc.).
        url: The target URL.
        params: Optional query parameters.
        json: Optional JSON body (will be serialized).
        headers: Optional extra headers merged with defaults.

    Returns:
        The ``httpx.Response`` object.

    Raises:
        HttpError: On HTTP errors (4xx/5xx), timeouts, or connection failures.
    """
    async with managed_client(profile) as client:
        try:
            response = await client.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HttpError(
                f"HTTP {exc.response.status_code} {method} {url}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise HttpError(f"Request timed out: {method} {url}: {exc}") from exc
        except httpx.ConnectError as exc:
            raise HttpError(f"Connection failed: {method} {url}: {exc}") from exc
        else:
            return response


async def get_bytes(
    profile: TerraForgeProfile,
    url: str,
    *,
    start: int | None = None,
    end: int | None = None,
) -> bytes:
    """Fetch raw bytes from a URL, optionally using an HTTP range request.

    Range requests are essential for cloud-native formats like COG where only
    a small portion of a large file needs to be read (e.g. magic bytes, overviews).

    Parameters:
        profile: The active TerraForge profile.
        url: The target URL.
        start: Start byte offset (inclusive). If ``None``, reads from the beginning.
        end: End byte offset (exclusive). If ``None``, reads to the end.

    Returns:
        The response body as raw bytes.

    Raises:
        HttpError: On HTTP errors, timeouts, or connection failures.
    """
    headers: dict[str, str] = {}
    if start is not None or end is not None:
        range_start = start if start is not None else ""
        range_end = end - 1 if end is not None else ""
        headers["Range"] = f"bytes={range_start}-{range_end}"

    async with managed_client(profile) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HttpError(
                f"HTTP {exc.response.status_code} fetching {url}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise HttpError(f"Timed out fetching {url}: {exc}") from exc
        except httpx.ConnectError as exc:
            raise HttpError(f"Connection failed fetching {url}: {exc}") from exc
        else:
            return response.content
