"""STAC multi-collection search -- Yosemite National Park.

Searches Element84 Earth Search for BOTH Sentinel-2 L2A AND Copernicus
DEM GLO-30 over Yosemite National Park, then renders a two-panel figure:
satellite scene footprints (left) and DEM elevation map with statistics
(right).

Output: examples/outputs/stac_multi_collection_yosemite.png

Data source: Sentinel-2 L2A + Copernicus DEM GLO-30 via Element84 Earth Search

Usage::

    python examples/scripts/stac_multi_collection_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
# Yosemite National Park
YOS_BBOX = [-119.8, 37.6, -119.4, 37.9]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "stac_multi_collection_yosemite.png"
OUTPUT_TXT = OUTPUT_DIR / "stac_multi_collection_yosemite.txt"


async def main() -> None:
    """Search two STAC collections over Yosemite and render combined figure."""
    print("EarthForge -- Multi-Collection STAC Demo: Yosemite NP")
    print("=" * 57)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Search both collections
    print("Searching for Sentinel-2 scenes over Yosemite...")
    s2_result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=YOS_BBOX,
        datetime_range="2025-06-01/2025-09-30",
        max_items=30,
    )
    print(f"  Sentinel-2: {len(s2_result.items)} items")

    print("Searching for COP DEM tiles over Yosemite...")
    dem_result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=YOS_BBOX,
        max_items=10,
    )
    print(f"  COP DEM: {len(dem_result.items)} items")

    if not s2_result.items and not dem_result.items:
        print("No items found in either collection.")
        return

    # Try to read a DEM tile
    dem_elevation = None
    dem_tile_id = None
    if dem_result.items:
        dem_item = dem_result.items[0]
        dem_tile_id = dem_item.id
        data_asset = next(
            (a for a in dem_item.assets if a.key in ("data", "visual", "default")),
            None,
        )
        if not data_asset and dem_item.assets:
            data_asset = dem_item.assets[0]

        if data_asset:
            print(f"Reading DEM tile: {dem_tile_id}...")
            try:
                import rasterio
                from rasterio.warp import transform_bounds
                from rasterio.windows import from_bounds

                with rasterio.open(data_asset.href) as src:
                    str(src.crs)
                    if src.crs and str(src.crs) != "EPSG:4326":
                        native_bounds = transform_bounds(
                            "EPSG:4326",
                            src.crs,
                            *YOS_BBOX,
                        )
                    else:
                        native_bounds = YOS_BBOX
                    window = from_bounds(*native_bounds, transform=src.transform)
                    dem_elevation = src.read(1, window=window).astype(np.float32)
                    nodata = src.nodata

                if nodata is not None:
                    dem_elevation[dem_elevation == nodata] = np.nan

                print(f"  Shape: {dem_elevation.shape}")
                print(
                    f"  Elevation: {np.nanmin(dem_elevation):.0f}m -- "
                    f"{np.nanmax(dem_elevation):.0f}m"
                )
            except Exception as exc:
                print(f"  Could not read DEM: {exc}")
                dem_elevation = None

    # Render two-panel figure
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import Normalize
        from matplotlib.patches import Rectangle
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, (ax_s2, ax_dem) = plt.subplots(1, 2, figsize=(16, 7))

    # ---- Left panel: Sentinel-2 footprints ----
    bbox_w = YOS_BBOX[2] - YOS_BBOX[0]
    bbox_h = YOS_BBOX[3] - YOS_BBOX[1]
    ax_s2.add_patch(
        Rectangle(
            (YOS_BBOX[0], YOS_BBOX[1]),
            bbox_w,
            bbox_h,
            linewidth=2,
            edgecolor="black",
            facecolor="lightgray",
            alpha=0.3,
            linestyle="--",
            label="Search bbox",
        )
    )

    cmap_s2 = plt.cm.viridis_r
    norm_s2 = Normalize(vmin=0, vmax=100)

    cloud_values = []
    for item in s2_result.items:
        cc = item.properties.get("eo:cloud_cover", 50)
        cloud_values.append(cc)
        color = cmap_s2(norm_s2(cc))
        if item.bbox and len(item.bbox) >= 4:
            w = item.bbox[2] - item.bbox[0]
            h = item.bbox[3] - item.bbox[1]
            ax_s2.add_patch(
                Rectangle(
                    (item.bbox[0], item.bbox[1]),
                    w,
                    h,
                    linewidth=0.8,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.35,
                )
            )

    ax_s2.set_xlim(YOS_BBOX[0] - 0.3, YOS_BBOX[2] + 0.3)
    ax_s2.set_ylim(YOS_BBOX[1] - 0.2, YOS_BBOX[3] + 0.2)
    ax_s2.set_aspect("equal")
    ax_s2.set_title(
        f"Sentinel-2 Scene Footprints\n{len(s2_result.items)} scenes | Jun-Sep 2025",
        fontsize=12,
        fontweight="bold",
    )
    ax_s2.set_xlabel("Longitude", fontsize=10)
    ax_s2.set_ylabel("Latitude", fontsize=10)

    sm = ScalarMappable(cmap=cmap_s2, norm=norm_s2)
    sm.set_array([])
    cbar_s2 = fig.colorbar(sm, ax=ax_s2, shrink=0.7, pad=0.02)
    cbar_s2.set_label("Cloud Cover (%)", fontsize=10)

    # ---- Right panel: DEM elevation ----
    if dem_elevation is not None:
        # Compute hillshade
        dy, dx = np.gradient(dem_elevation)
        slope = np.arctan(np.sqrt(dx**2 + dy**2))
        aspect = np.arctan2(-dy, dx)
        shade = np.clip(
            np.sin(np.radians(45)) * np.cos(slope)
            + np.cos(np.radians(45)) * np.sin(slope) * np.cos(np.radians(315) - aspect),
            0,
            1,
        )

        lons = np.linspace(YOS_BBOX[0], YOS_BBOX[2], dem_elevation.shape[1])
        lats = np.linspace(YOS_BBOX[3], YOS_BBOX[1], dem_elevation.shape[0])

        im = ax_dem.imshow(
            dem_elevation,
            extent=[lons.min(), lons.max(), lats.min(), lats.max()],
            cmap="cividis",
            aspect="auto",
        )
        ax_dem.imshow(
            shade,
            extent=[lons.min(), lons.max(), lats.min(), lats.max()],
            cmap="gray",
            alpha=0.35,
            aspect="auto",
        )
        ax_dem.set_title(
            f"Copernicus DEM 30m\nTile: {dem_tile_id}",
            fontsize=12,
            fontweight="bold",
        )
        ax_dem.set_xlabel("Longitude", fontsize=10)
        ax_dem.set_ylabel("Latitude", fontsize=10)

        cbar_dem = fig.colorbar(im, ax=ax_dem, shrink=0.7, pad=0.02)
        cbar_dem.set_label("Elevation (m)", fontsize=10)

        # Stats overlay
        elev_min = float(np.nanmin(dem_elevation))
        elev_max = float(np.nanmax(dem_elevation))
        elev_mean = float(np.nanmean(dem_elevation))
        stats_text = (
            f"Min: {elev_min:.0f}m\n"
            f"Max: {elev_max:.0f}m\n"
            f"Mean: {elev_mean:.0f}m\n"
            f"Relief: {elev_max - elev_min:.0f}m"
        )
        ax_dem.text(
            0.02,
            0.02,
            stats_text,
            transform=ax_dem.transAxes,
            fontsize=9,
            fontfamily="monospace",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.85},
        )
    else:
        ax_dem.text(
            0.5,
            0.5,
            "DEM tile could not be loaded",
            transform=ax_dem.transAxes,
            ha="center",
            va="center",
            fontsize=12,
        )
        ax_dem.set_title("Copernicus DEM 30m\n(not available)", fontsize=12)
        elev_min = elev_max = elev_mean = 0.0

    fig.suptitle(
        "Multi-Collection STAC Search -- Yosemite National Park",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )

    fig.text(
        0.5,
        0.01,
        f"Data: Copernicus Sentinel-2 + DEM GLO-30 via Earth Search | "
        f"Palettes: viridis, cividis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center",
        fontsize=7,
        color="gray",
    )

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    mean_cc = np.mean(cloud_values) if cloud_values else 0
    sidecar = (
        f"Alt Text: Two-panel figure combining data from two STAC collections "
        f"over Yosemite National Park. Left panel shows {len(s2_result.items)} "
        f"Sentinel-2 scene footprints color-coded by cloud cover (mean {mean_cc:.1f}%) "
        f"using reversed viridis palette. Right panel shows Copernicus DEM 30m "
        f"terrain with cividis palette and hillshade, elevations from "
        f"{elev_min:.0f}m to {elev_max:.0f}m.\n\n"
        f"Data Sources:\n"
        f"  1. Copernicus, Sentinel-2 Level-2A\n"
        f"  2. Copernicus, DEM GLO-30\n"
        f"URL: {STAC_API}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms / Copernicus DEM License\n"
        f"Spatial Extent: {YOS_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/stac_multi_collection_demo.py\n"
        f"Parameters: collections=[sentinel-2-l2a, cop-dem-glo-30], bbox={YOS_BBOX}\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
