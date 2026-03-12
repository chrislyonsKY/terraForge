"""STAC item and collection metadata inspection.

Fetches and parses STAC items or collections from a URL, returning structured
metadata suitable for CLI rendering. Uses httpx via ``earthforge.core.http``
for fetching (unlike search, which uses pystac-client).

Usage::

    from earthforge.stac.info import inspect_stac_item

    profile = await load_profile("default")
    info = await inspect_stac_item(profile, "https://earth-search.../items/S2A_...")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from earthforge.core.http import request
from earthforge.stac.errors import StacError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile


class StacAssetDetail(BaseModel):
    """Detailed metadata for a single STAC asset.

    Attributes:
        key: Asset key identifier.
        href: URL to the asset.
        media_type: MIME type.
        title: Human-readable title.
        roles: Asset roles (e.g. ``["data"]``, ``["thumbnail"]``).
    """

    key: str = Field(title="Key")
    href: str = Field(title="URL")
    media_type: str | None = Field(default=None, title="Type")
    title: str | None = Field(default=None, title="Title")
    roles: list[str] = Field(default_factory=list, title="Roles")


class StacItemInfo(BaseModel):
    """Structured metadata for a STAC item.

    Attributes:
        id: STAC item ID.
        collection: Parent collection ID.
        datetime: Item datetime as ISO string.
        bbox: Bounding box ``[west, south, east, north]``.
        geometry_type: GeoJSON geometry type (e.g. ``"Polygon"``).
        properties: Selected properties from the item.
        asset_count: Number of assets.
        assets: Detailed asset metadata.
        stac_version: STAC specification version.
        stac_extensions: List of STAC extension URIs.
    """

    id: str = Field(title="ID")
    collection: str | None = Field(default=None, title="Collection")
    datetime: str | None = Field(default=None, title="Datetime")
    bbox: list[float] | None = Field(default=None, title="Bounding Box")
    geometry_type: str | None = Field(default=None, title="Geometry")
    properties: dict[str, object] = Field(default_factory=dict, title="Properties")
    asset_count: int = Field(default=0, title="Assets")
    assets: list[StacAssetDetail] = Field(default_factory=list, title="Asset Details")
    stac_version: str | None = Field(default=None, title="STAC Version")
    stac_extensions: list[str] = Field(default_factory=list, title="Extensions")


class StacCollectionInfo(BaseModel):
    """Structured metadata for a STAC collection.

    Attributes:
        id: Collection ID.
        title: Human-readable title.
        description: Collection description.
        license: License identifier.
        extent_spatial: Spatial extent as bounding box.
        extent_temporal: Temporal extent as ``[start, end]`` ISO strings.
        item_count: Number of items if reported.
        stac_version: STAC specification version.
    """

    id: str = Field(title="ID")
    title: str | None = Field(default=None, title="Title")
    description: str | None = Field(default=None, title="Description")
    license: str | None = Field(default=None, title="License")
    extent_spatial: list[float] | None = Field(default=None, title="Spatial Extent")
    extent_temporal: list[str | None] = Field(default_factory=list, title="Temporal Extent")
    item_count: int | None = Field(default=None, title="Items")
    stac_version: str | None = Field(default=None, title="STAC Version")


async def inspect_stac_item(profile: EarthForgeProfile, url: str) -> StacItemInfo:
    """Fetch and parse a STAC item from a URL.

    Parameters:
        profile: Active configuration profile.
        url: URL to a STAC item JSON document.

    Returns:
        Structured item metadata.

    Raises:
        StacError: If the fetch fails or the response is not a valid STAC item.
    """
    try:
        response = await request(profile, "GET", url)
        data: dict[str, Any] = response.json()
    except Exception as exc:
        raise StacError(f"Failed to fetch STAC item from {url}: {exc}") from exc

    if data.get("type") != "Feature":
        raise StacError(f"URL does not point to a STAC item (type={data.get('type')!r})")

    # Extract properties subset — include date range fields (STAC best practices)
    # and common EO/SAR extensions
    props = data.get("properties", {})
    selected_props: dict[str, object] = {}
    prop_keys = (
        "datetime",
        "start_datetime",
        "end_datetime",
        "eo:cloud_cover",
        "eo:bands",
        "platform",
        "constellation",
        "instruments",
        "gsd",
        "proj:epsg",
        "proj:shape",
        "sar:instrument_mode",
        "sar:frequency_band",
        "created",
        "updated",
    )
    for key in prop_keys:
        if key in props:
            selected_props[key] = props[key]

    # Extract assets
    raw_assets = data.get("assets", {})
    assets = [
        StacAssetDetail(
            key=key,
            href=asset.get("href", ""),
            media_type=asset.get("type"),
            title=asset.get("title"),
            roles=asset.get("roles", []),
        )
        for key, asset in raw_assets.items()
    ]

    geometry = data.get("geometry", {})

    return StacItemInfo(
        id=data.get("id", ""),
        collection=data.get("collection"),
        datetime=props.get("datetime"),
        bbox=data.get("bbox"),
        geometry_type=geometry.get("type") if isinstance(geometry, dict) else None,
        properties=selected_props,
        asset_count=len(raw_assets),
        assets=assets,
        stac_version=data.get("stac_version"),
        stac_extensions=data.get("stac_extensions", []),
    )


async def inspect_stac_collection(profile: EarthForgeProfile, url: str) -> StacCollectionInfo:
    """Fetch and parse a STAC collection from a URL.

    Parameters:
        profile: Active configuration profile.
        url: URL to a STAC collection JSON document.

    Returns:
        Structured collection metadata.

    Raises:
        StacError: If the fetch fails or the response is not a valid STAC collection.
    """
    try:
        response = await request(profile, "GET", url)
        data: dict[str, Any] = response.json()
    except Exception as exc:
        raise StacError(f"Failed to fetch STAC collection from {url}: {exc}") from exc

    if data.get("type") not in ("Collection", None):
        raise StacError(f"URL does not point to a STAC collection (type={data.get('type')!r})")

    # Extract extents
    extent = data.get("extent", {})
    spatial = extent.get("spatial", {})
    temporal = extent.get("temporal", {})

    spatial_bbox: list[float] | None = None
    if spatial_bboxes := spatial.get("bbox"):
        if spatial_bboxes and isinstance(spatial_bboxes[0], list):
            spatial_bbox = [float(v) for v in spatial_bboxes[0]]

    temporal_interval: list[str | None] = []
    if temporal_intervals := temporal.get("interval"):
        if temporal_intervals and isinstance(temporal_intervals[0], list):
            temporal_interval = temporal_intervals[0]

    return StacCollectionInfo(
        id=data.get("id", ""),
        title=data.get("title"),
        description=data.get("description"),
        license=data.get("license"),
        extent_spatial=spatial_bbox,
        extent_temporal=temporal_interval,
        item_count=data.get("numberMatched"),
        stac_version=data.get("stac_version"),
    )
