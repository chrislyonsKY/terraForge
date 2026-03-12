"""STAC catalog search.

Wraps pystac-client's search functionality with EarthForge's profile-aware
configuration and returns structured Pydantic models. The search is executed
synchronously via pystac-client (which uses ``requests`` internally) and
wrapped in an async interface for consistency with the rest of EarthForge.

Design note: pystac-client uses ``requests`` for HTTP, not ``httpx``. This is
an accepted trade-off — pystac-client handles STAC pagination, conformance
negotiation, and CQL2 filtering that would be complex to reimplement. Our
httpx-based ``earthforge.core.http`` is used for non-STAC HTTP operations
(range reads, direct asset fetches).

Usage::

    from earthforge.core.config import load_profile
    from earthforge.stac.search import search_catalog

    profile = await load_profile("default")
    results = await search_catalog(
        profile=profile,
        collections=["sentinel-2-l2a"],
        bbox=[-85.0, 37.0, -84.0, 38.0],
        max_items=10,
    )
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from earthforge.stac.errors import StacError, StacSearchError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile

logger = logging.getLogger(__name__)


class AssetInfo(BaseModel):
    """Metadata for a single STAC asset.

    Attributes:
        key: The asset key (e.g. ``"visual"``, ``"B04"``).
        href: URL to the asset file.
        media_type: MIME type if available.
        title: Human-readable title if available.
    """

    key: str = Field(title="Key")
    href: str = Field(title="URL")
    media_type: str | None = Field(default=None, title="Type")
    title: str | None = Field(default=None, title="Title")


class SearchResultItem(BaseModel):
    """A single STAC item from a search result.

    Attributes:
        id: The STAC item ID.
        collection: The collection this item belongs to.
        datetime: The item's datetime as ISO string, or ``None`` for date ranges.
        bbox: Bounding box ``[west, south, east, north]``.
        asset_count: Number of assets in this item.
        assets: List of asset metadata (populated when detail is requested).
        self_link: URL to the item's self link.
    """

    id: str = Field(title="ID")
    collection: str | None = Field(default=None, title="Collection")
    datetime: str | None = Field(default=None, title="Datetime")
    bbox: list[float] | None = Field(default=None, title="Bounding Box")
    asset_count: int = Field(default=0, title="Assets")
    assets: list[AssetInfo] = Field(default_factory=list, title="Asset Details")
    self_link: str | None = Field(default=None, title="Self Link")


class SearchResult(BaseModel):
    """Structured result from a STAC catalog search.

    Attributes:
        api_url: The STAC API endpoint that was searched.
        matched: Total number of items matching the query (if reported by API).
        returned: Number of items actually returned.
        items: The search result items.
    """

    api_url: str = Field(title="API URL")
    matched: int | None = Field(default=None, title="Matched")
    returned: int = Field(title="Returned")
    items: list[SearchResultItem] = Field(title="Items")


def _do_search(
    api_url: str,
    collections: list[str] | None,
    bbox: list[float] | None,
    datetime_range: str | None,
    max_items: int,
    query: dict[str, object] | None,
    filter_expr: dict[str, object] | None,
    filter_lang: str | None,
) -> SearchResult:
    """Execute a STAC search synchronously via pystac-client.

    Parameters:
        api_url: STAC API root URL.
        collections: Collection IDs to filter by.
        bbox: Bounding box ``[west, south, east, north]``.
        datetime_range: ISO 8601 datetime or range (e.g. ``"2024-01-01/2024-12-31"``).
        max_items: Maximum number of items to return.
        query: Legacy query parameters (deprecated in favor of CQL2).
        filter_expr: CQL2-JSON filter expression (preferred over ``query``).
        filter_lang: Filter language identifier (e.g. ``"cql2-json"``).

    Returns:
        Structured search result.

    Raises:
        StacSearchError: If the search fails.
    """
    try:
        from pystac_client import Client
    except ImportError as exc:
        msg = "pystac-client is required for STAC operations: pip install earthforge[stac]"
        raise StacError(msg) from exc

    try:
        catalog = Client.open(api_url)
    except Exception as exc:
        raise StacSearchError(f"Failed to connect to STAC API at {api_url}: {exc}") from exc

    try:
        search_kwargs: dict[str, object] = {
            "collections": collections,
            "bbox": bbox,
            "datetime": datetime_range,
            "max_items": max_items,
        }
        # Prefer CQL2 filter over legacy query parameter
        if filter_expr:
            search_kwargs["filter"] = filter_expr
            if filter_lang:
                search_kwargs["filter_lang"] = filter_lang
        elif query:
            search_kwargs["query"] = query
        search = catalog.search(**search_kwargs)  # type: ignore[arg-type]

        item_collection = search.item_collection()
    except Exception as exc:
        raise StacSearchError(f"STAC search failed: {exc}") from exc

    # Extract matched count if available
    matched: int | None = None
    try:
        matched = search.matched()
    except Exception:  # noqa: S110 — not all APIs report matched count
        pass

    # Convert pystac items to our models
    items: list[SearchResultItem] = []
    for item in item_collection:
        # Extract datetime
        dt_str: str | None = None
        if item.datetime is not None:
            dt_str = (
                item.datetime.isoformat()
                if isinstance(item.datetime, datetime)
                else str(item.datetime)
            )
        elif item.properties.get("datetime"):
            dt_str = str(item.properties["datetime"])

        # Extract assets
        assets = [
            AssetInfo(
                key=key,
                href=asset.href,
                media_type=asset.media_type,
                title=asset.title,
            )
            for key, asset in item.assets.items()
        ]

        # Find self link
        self_link: str | None = None
        for link in item.links:
            if link.rel == "self":
                self_link = link.href
                break

        items.append(
            SearchResultItem(
                id=item.id,
                collection=item.collection_id,
                datetime=dt_str,
                bbox=list(item.bbox) if item.bbox else None,
                asset_count=len(item.assets),
                assets=assets,
                self_link=self_link,
            )
        )

    return SearchResult(
        api_url=api_url,
        matched=matched,
        returned=len(items),
        items=items,
    )


async def search_catalog(
    profile: EarthForgeProfile,
    *,
    collections: list[str] | None = None,
    bbox: list[float] | None = None,
    datetime_range: str | None = None,
    max_items: int = 10,
    query: dict[str, object] | None = None,
    filter_expr: dict[str, object] | None = None,
    filter_lang: str | None = "cql2-json",
) -> SearchResult:
    """Search a STAC catalog using the profile's configured API endpoint.

    Runs the synchronous pystac-client search in a thread executor to avoid
    blocking the event loop.

    Parameters:
        profile: Active configuration profile (provides the STAC API URL).
        collections: Collection IDs to search within (e.g. ``["sentinel-2-l2a"]``).
        bbox: Spatial bounding box ``[west, south, east, north]`` in WGS84.
        datetime_range: Temporal filter as ISO 8601 datetime or range string.
        max_items: Maximum items to return (default: 10).
        query: Legacy query parameters (deprecated — use ``filter_expr`` instead).
        filter_expr: CQL2-JSON filter expression, preferred per STAC best practices.
            Example: ``{"op": "<=", "args": [{"property": "eo:cloud_cover"}, 20]}``
        filter_lang: Filter language (default: ``"cql2-json"``). Only used when
            ``filter_expr`` is provided.

    Returns:
        Structured search results with items and metadata.

    Raises:
        StacError: If pystac-client is not installed.
        StacSearchError: If the API connection or search fails.
    """
    if not profile.stac_api:
        raise StacError(
            f"Profile {profile.name!r} has no stac_api configured. "
            f"Set stac_api in your profile or use a profile with a STAC endpoint."
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _do_search,
            api_url=profile.stac_api,
            collections=collections,
            bbox=bbox,
            datetime_range=datetime_range,
            max_items=max_items,
            query=query,
            filter_expr=filter_expr,
            filter_lang=filter_lang,
        ),
    )
