"""STAC footprint query — real Sentinel-2 scene footprints queried by bbox.

Demonstrates vector query capabilities using real STAC search results.
Searches Element84 Earth Search for Sentinel-2 scenes, creates a GeoJSON
of footprints, then queries by spatial extent.

Output: examples/outputs/stac_footprints_query_ky.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/vector_query_overture_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/stac/src")
sys.path.insert(0, "packages/vector/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.core.palettes import SET2
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
KY_BBOX = [-85.5, 37.0, -84.0, 38.5]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "stac_footprints_query_ky.png"
OUTPUT_TXT = OUTPUT_DIR / "stac_footprints_query_ky.txt"


async def main() -> None:
    """Query real STAC footprints by bbox."""
    print("EarthForge — Vector Query Demo: Real STAC Footprints")
    print("=" * 55)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Search for real Sentinel-2 scenes across multiple months
    print("Searching for Sentinel-2 scenes (Jun-Sep 2025)...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=KY_BBOX,
        datetime_range="2025-06-01/2025-09-30",
        max_items=40,
    )
    print(f"Found {len(result.items)} items")

    if not result.items:
        print("No items found. Check network.")
        return

    try:
        import geopandas as gpd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from shapely.geometry import box
    except ImportError as e:
        print(f"Required: pip install geopandas matplotlib shapely ({e})")
        return

    # Build GeoDataFrame from real search results
    features = []
    for item in result.items:
        if not item.bbox:
            continue
        w, s, e, n = item.bbox
        cc = item.properties.get("eo:cloud_cover", 50)
        month = (item.datetime or "unknown")[:7]
        features.append({
            "geometry": box(w, s, e, n),
            "id": item.id,
            "cloud_cover": cc,
            "datetime": item.datetime or "",
            "month": month,
            "platform": item.properties.get("platform", ""),
        })

    gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
    print(f"Built GeoDataFrame: {len(gdf)} footprints")

    # Classify by cloud cover
    gdf["cc_class"] = "clear"
    gdf.loc[gdf["cloud_cover"] > 20, "cc_class"] = "partly cloudy"
    gdf.loc[gdf["cloud_cover"] > 50, "cc_class"] = "cloudy"
    gdf.loc[gdf["cloud_cover"] > 80, "cc_class"] = "overcast"

    # Render
    print("Rendering map...")
    fig, ax = plt.subplots(figsize=(10, 8))

    set2_rgb = [
        tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
        for h in SET2[:4]
    ]
    class_colors = {
        "clear": set2_rgb[0],
        "partly cloudy": set2_rgb[1],
        "cloudy": set2_rgb[2],
        "overcast": set2_rgb[3],
    }

    for cls, color in class_colors.items():
        subset = gdf[gdf["cc_class"] == cls]
        if len(subset) > 0:
            subset.plot(
                ax=ax, color=color, edgecolor="gray",
                linewidth=0.5, alpha=0.5, label=f"{cls} ({len(subset)})",
            )

    # Draw study area bbox
    study = gpd.GeoDataFrame(
        [{"geometry": box(*KY_BBOX)}], crs="EPSG:4326"
    )
    study.boundary.plot(ax=ax, color="black", linewidth=2, linestyle="--")

    ax.legend(loc="upper right", fontsize=9, title="Cloud Cover Class")
    ax.set_title(
        f"Sentinel-2 Scene Footprints — Central Kentucky\n"
        f"Jun-Sep 2025 | {len(gdf)} scenes from Earth Search",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search (real API query) | "
        f"Palette: Set2 (colorblind-safe) | EarthForge v1.0.0 | "
        f"{datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: Map of {len(gdf)} Sentinel-2 scene footprints over Central "
        f"Kentucky from June-September 2025, classified by cloud cover into "
        f"four categories using the ColorBrewer Set2 palette. A dashed rectangle "
        f"marks the Kentucky study area bounding box.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {STAC_API}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {KY_BBOX}\n"
        f"Temporal Extent: 2025-06-01 / 2025-09-30\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/vector_query_overture_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={KY_BBOX}, max_items=40\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
