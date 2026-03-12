"""KyFromAbove STAC API demo.

Demonstrates EarthForge's STAC search, item inspection, collection browsing,
raster info, and COG validation against Kentucky's KyFromAbove STAC catalog.

The KyFromAbove program provides aerial imagery and LiDAR-derived elevation
data for the Commonwealth of Kentucky as Cloud-Optimized GeoTIFFs (COGs).

STAC Browser: https://kygeonet.ky.gov/stac/
Data Index:   https://kyfromabove.s3.us-west-2.amazonaws.com/index.html

Usage::

    python examples/kygeonet_stac_demo.py
"""

from __future__ import annotations

import asyncio
import json

from earthforge.core.config import EarthForgeProfile
from earthforge.raster.info import inspect_raster
from earthforge.raster.validate import validate_cog
from earthforge.stac.info import inspect_stac_collection, inspect_stac_item
from earthforge.stac.search import search_catalog

# The actual STAC API endpoint behind the kygeonet.ky.gov browser
STAC_API = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com/"

# Bounding box around Frankfort, KY (state capital)
FRANKFORT_BBOX = [-84.9, 38.15, -84.8, 38.25]


async def demo_list_collections() -> None:
    """Show available collections via collection info."""
    print("=" * 60)
    print("COLLECTION INFO: orthos-phase2")
    print("=" * 60)

    profile = EarthForgeProfile(name="kygeonet", stac_api=STAC_API)
    info = await inspect_stac_collection(
        profile, f"{STAC_API}collections/orthos-phase2"
    )
    print(f"  ID:       {info.id}")
    print(f"  Title:    {info.title}")
    print(f"  License:  {info.license}")
    print(f"  Spatial:  {info.extent_spatial}")
    print(f"  Temporal: {info.extent_temporal}")
    print()


async def demo_search_dem() -> None:
    """Search for DEM tiles near Frankfort, KY."""
    print("=" * 60)
    print("STAC SEARCH: DEM Phase 2 near Frankfort, KY")
    print("=" * 60)

    profile = EarthForgeProfile(name="kygeonet", stac_api=STAC_API)
    result = await search_catalog(
        profile,
        collections=["dem-phase2"],
        bbox=FRANKFORT_BBOX,
        max_items=3,
    )

    print(f"  Returned: {result.returned} items")
    for item in result.items:
        print(f"  - {item.id}")
        print(f"    bbox: {item.bbox}")
        for asset in item.assets:
            print(f"    asset [{asset.key}]: {asset.href}")
    print()

    return result


async def demo_item_info(item_url: str) -> None:
    """Inspect a single STAC item."""
    print("=" * 60)
    print(f"ITEM INFO: {item_url.split('/')[-1]}")
    print("=" * 60)

    profile = EarthForgeProfile(name="kygeonet", stac_api=STAC_API)
    info = await inspect_stac_item(profile, item_url)

    print(f"  ID:         {info.id}")
    print(f"  Collection: {info.collection}")
    print(f"  DateTime:   {info.datetime}")
    print(f"  BBox:       {info.bbox}")
    print(f"  Geometry:   {info.geometry_type}")
    print(f"  Properties: {json.dumps(info.properties, indent=4)}")
    print(f"  Assets:     {[(a.key, a.media_type) for a in info.assets]}")
    print()


async def demo_raster_info_and_validate(cog_url: str) -> None:
    """Run raster info and COG validation on a remote COG."""
    print("=" * 60)
    print(f"RASTER INFO + COG VALIDATE: {cog_url.split('/')[-1]}")
    print("=" * 60)

    info = await inspect_raster(cog_url)
    print(f"  Driver:      {info.driver}")
    print(f"  Size:        {info.width} x {info.height}")
    print(f"  Bands:       {info.band_count}")
    print(f"  CRS:         {info.crs}")
    print(f"  Compression: {info.compression}")
    print(f"  Tiled:       {info.is_tiled} ({info.tile_width}x{info.tile_height})")
    print(f"  Overviews:   {info.overview_count} levels={info.overview_levels}")
    print()

    result = await validate_cog(cog_url)
    print(f"  COG Valid:   {result.is_valid}")
    print(f"  Summary:     {result.summary}")
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"    [{status}] {check.name}: {check.message}")
    print()


async def main() -> None:
    """Run all demos sequentially."""
    print()
    print("EarthForge — KyFromAbove STAC Demo")
    print("===================================")
    print()

    await demo_list_collections()

    result = await demo_search_dem()

    if result and result.items:
        first = result.items[0]
        if first.self_link:
            await demo_item_info(first.self_link)

        # Find the COG asset URL
        cog_assets = [a for a in first.assets if a.key == "asset"]
        if cog_assets:
            await demo_raster_info_and_validate(cog_assets[0].href)

    print("Demo complete.")


if __name__ == "__main__":
    asyncio.run(main())
