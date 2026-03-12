"""STAC asset download with parallel fetch and resume support.

Downloads assets from a STAC item to a local directory. Fetches the item JSON,
filters the requested assets, then downloads them concurrently using
``asyncio.TaskGroup`` bounded by a semaphore for configurable parallelism.

Resume support: if a local file already exists with the same byte count as
the server's ``Content-Length``, the asset is skipped without re-downloading.

Usage::

    from earthforge.stac.fetch import fetch_assets

    profile = await load_profile("default")
    result = await fetch_assets(
        profile,
        item_url="https://earth-search.../items/S2A_...",
        output_dir="./data/sentinel2",
        assets=["red", "green", "blue"],
        parallel=4,
    )
    print(f"Downloaded {result.assets_fetched} assets ({result.total_bytes_downloaded:,} bytes)")
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, Field

from earthforge.core.errors import EarthForgeError
from earthforge.core.http import managed_client, request
from earthforge.stac.errors import StacError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile

logger = logging.getLogger(__name__)

#: Assets with these roles are excluded from the default "all assets" download.
_EXCLUDED_ROLES: frozenset[str] = frozenset({"thumbnail", "overview"})


class AssetFetchResult(BaseModel):
    """Result for a single downloaded asset.

    Attributes:
        key: Asset dictionary key (e.g. ``"B04"``, ``"red"``).
        href: Original remote URL of the asset.
        local_path: Path to the downloaded local file.
        size_bytes: File size in bytes.
        skipped: True if the file already existed with the correct size (resumed).
        media_type: MIME type from the STAC asset definition.
    """

    key: str = Field(title="Asset Key")
    href: str = Field(title="Remote URL")
    local_path: str = Field(title="Local Path")
    size_bytes: int = Field(title="Size (bytes)")
    skipped: bool = Field(default=False, title="Skipped (resumed)")
    media_type: str | None = Field(default=None, title="Media Type")


class FetchResult(BaseModel):
    """Structured result for a STAC asset fetch operation.

    Attributes:
        item_id: STAC item ID.
        item_url: URL the item was fetched from.
        output_dir: Local directory where assets were written.
        assets_requested: Number of assets selected for download.
        assets_fetched: Number of assets actually downloaded.
        assets_skipped: Number of assets skipped (already existed, correct size).
        total_bytes_downloaded: Bytes transferred during this run.
        total_size_bytes: Total size of all files on disk after fetch.
        elapsed_seconds: Wall-clock time for the entire operation.
        files: Per-asset download results.
    """

    item_id: str = Field(title="Item ID")
    item_url: str = Field(title="Item URL")
    output_dir: str = Field(title="Output Directory")
    assets_requested: int = Field(title="Assets Requested")
    assets_fetched: int = Field(title="Assets Downloaded")
    assets_skipped: int = Field(title="Assets Skipped")
    total_bytes_downloaded: int = Field(title="Bytes Downloaded")
    total_size_bytes: int = Field(title="Total Size (bytes)")
    elapsed_seconds: float = Field(title="Elapsed (s)")
    files: list[AssetFetchResult] = Field(default_factory=list, title="Files")


def _select_assets(
    item_assets: dict[str, Any],
    requested: list[str] | None,
) -> dict[str, Any]:
    """Select which assets to download.

    If ``requested`` is provided, only those keys are returned (unknown keys
    are silently skipped with a debug log). If ``requested`` is None, all assets
    are returned except those whose ``roles`` list contains an excluded role
    (``thumbnail``, ``overview``).

    Parameters:
        item_assets: The ``assets`` dict from the STAC item JSON.
        requested: Explicit list of asset keys, or ``None`` for all data assets.

    Returns:
        Filtered dict of asset key → asset dict.
    """
    if requested is not None:
        result: dict[str, Any] = {}
        for key in requested:
            if key in item_assets:
                result[key] = item_assets[key]
            else:
                logger.debug("Requested asset key %r not found in item — skipping", key)
        return result

    # Default: exclude thumbnail/overview roles
    return {
        key: asset
        for key, asset in item_assets.items()
        if not frozenset(asset.get("roles", [])) & _EXCLUDED_ROLES
    }


async def _download_asset(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    key: str,
    asset: dict[str, Any],
    output_dir: Path,
) -> AssetFetchResult:
    """Download a single asset to ``output_dir``.

    Uses the semaphore to cap concurrent downloads. Checks the remote
    ``Content-Length`` header: if the local file already exists with the same
    byte count, the download is skipped (resume support).

    Parameters:
        client: Shared ``httpx.AsyncClient``.
        semaphore: Concurrency limiter.
        key: Asset key (used as filename stem if URL has no clean name).
        asset: Asset dict from the STAC item (must contain ``href``).
        output_dir: Directory to write the file into.

    Returns:
        :class:`AssetFetchResult` describing the outcome.

    Raises:
        StacError: On HTTP failure or I/O error.
    """
    href = asset.get("href", "")
    if not href:
        raise StacError(f"Asset '{key}' has no href")

    media_type: str | None = asset.get("type")

    # Derive a local filename from the URL path
    url_path = href.split("?")[0]  # strip query params
    filename = Path(url_path).name or f"{key}.bin"
    local_path = output_dir / filename

    async with semaphore:
        try:
            # HEAD request to get Content-Length for resume check
            head_resp = await client.head(href, follow_redirects=True)
            remote_size: int | None = None
            if head_resp.status_code == 200:
                cl = head_resp.headers.get("content-length")
                if cl and cl.isdigit():
                    remote_size = int(cl)

            # Resume: skip if local file matches remote size
            if remote_size is not None and local_path.exists():
                local_size = local_path.stat().st_size
                if local_size == remote_size:
                    logger.debug("Skipping %s — already complete (%d bytes)", key, local_size)
                    return AssetFetchResult(
                        key=key,
                        href=href,
                        local_path=str(local_path),
                        size_bytes=local_size,
                        skipped=True,
                        media_type=media_type,
                    )

            # Full download using streaming to handle large files
            logger.debug("Downloading %s → %s", href, local_path)
            async with client.stream("GET", href, follow_redirects=True) as response:
                response.raise_for_status()
                output_dir.mkdir(parents=True, exist_ok=True)
                with local_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        fh.write(chunk)

        except httpx.HTTPStatusError as exc:
            raise StacError(
                f"HTTP {exc.response.status_code} downloading asset '{key}' from {href}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise StacError(f"Timeout downloading asset '{key}': {exc}") from exc
        except httpx.ConnectError as exc:
            raise StacError(f"Connection error downloading asset '{key}': {exc}") from exc
        except OSError as exc:
            raise StacError(f"I/O error writing '{local_path}': {exc}") from exc

    size_bytes = local_path.stat().st_size
    return AssetFetchResult(
        key=key,
        href=href,
        local_path=str(local_path),
        size_bytes=size_bytes,
        skipped=False,
        media_type=media_type,
    )


async def fetch_assets(
    profile: EarthForgeProfile,
    item_url: str,
    *,
    output_dir: str | None = None,
    assets: list[str] | None = None,
    parallel: int = 4,
) -> FetchResult:
    """Download assets from a STAC item to a local directory.

    Fetches the item JSON from ``item_url``, selects the requested assets,
    then downloads them concurrently. Supports resume: assets that already
    exist locally with the correct byte count are skipped.

    Parameters:
        profile: EarthForge config profile (for HTTP client config).
        item_url: URL to a STAC item JSON.
        output_dir: Local directory to write files into. Defaults to
            ``<current_dir>/<item_id>/``.
        assets: List of asset keys to download. If ``None``, all data assets
            (excluding thumbnails and overviews) are downloaded.
        parallel: Maximum number of concurrent downloads (default: 4).

    Returns:
        :class:`FetchResult` with per-asset download details.

    Raises:
        StacError: If the item URL cannot be fetched or assets fail to download.
    """
    t_start = time.perf_counter()

    # Fetch the STAC item JSON
    try:
        response = await request(profile, "GET", item_url)
    except EarthForgeError as exc:
        raise StacError(f"Failed to fetch STAC item from {item_url}: {exc}") from exc

    try:
        item: dict[str, Any] = response.json()
    except Exception as exc:
        raise StacError(f"Invalid JSON from {item_url}: {exc}") from exc

    item_id: str = item.get("id", "unknown")
    item_assets: dict[str, Any] = item.get("assets", {})

    if not item_assets:
        raise StacError(f"STAC item '{item_id}' has no assets")

    # Resolve output directory
    out_dir = Path(output_dir) if output_dir else Path.cwd() / item_id

    # Select assets
    selected = _select_assets(item_assets, assets)
    if not selected:
        raise StacError(
            f"No matching assets found in item '{item_id}'. "
            f"Available keys: {list(item_assets.keys())}"
        )

    # Download all selected assets in parallel
    semaphore = asyncio.Semaphore(parallel)
    asset_results: list[AssetFetchResult] = []

    async with managed_client(profile) as client:
        async with asyncio.TaskGroup() as tg:
            tasks = {
                key: tg.create_task(_download_asset(client, semaphore, key, asset, out_dir))
                for key, asset in selected.items()
            }

    for key, task in tasks.items():
        try:
            asset_results.append(task.result())
        except Exception as exc:
            logger.warning("Asset '%s' failed: %s", key, exc)
            # Still record a failed result rather than aborting the entire fetch
            href = selected.get(key, {}).get("href", "")
            asset_results.append(
                AssetFetchResult(
                    key=key,
                    href=href,
                    local_path="",
                    size_bytes=0,
                    skipped=False,
                    media_type=None,
                )
            )

    elapsed = time.perf_counter() - t_start

    fetched = [r for r in asset_results if not r.skipped and r.size_bytes > 0]
    skipped = [r for r in asset_results if r.skipped]

    return FetchResult(
        item_id=item_id,
        item_url=item_url,
        output_dir=str(out_dir),
        assets_requested=len(selected),
        assets_fetched=len(fetched),
        assets_skipped=len(skipped),
        total_bytes_downloaded=sum(r.size_bytes for r in fetched),
        total_size_bytes=sum(r.size_bytes for r in asset_results if r.size_bytes > 0),
        elapsed_seconds=round(elapsed, 3),
        files=asset_results,
    )
