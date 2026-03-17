"""STAC Copernicus DEM -- Denali / Alaska Range elevation analysis.

Searches Element84 Earth Search for Copernicus DEM 30m tiles over the
Denali / Alaska Range, reads a DEM tile, and renders an elevation map
with statistics and a histogram.

Output: examples/outputs/dem_stats_denali_alaska.png

Data source: Copernicus DEM GLO-30 via Element84 Earth Search (public)

Usage::

    python examples/scripts/stac_copdem_alaska_demo.py
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
# Denali / Alaska Range
DENALI_BBOX = [-151.5, 62.8, -150.5, 63.2]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "dem_stats_denali_alaska.png"
OUTPUT_TXT = OUTPUT_DIR / "dem_stats_denali_alaska.txt"


async def main() -> None:
    """Search COP DEM tiles over Denali and render elevation analysis."""
    print("EarthForge -- STAC DEM Demo: Denali / Alaska Range")
    print("=" * 55)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for Copernicus DEM tiles over Denali...")
    result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=DENALI_BBOX,
        max_items=20,
    )

    print(f"Found {len(result.items)} DEM tiles")
    if not result.items:
        print("No tiles found. Check network connectivity.")
        return

    # Pick the first tile that has a data asset
    item = result.items[0]
    print(f"Selected tile: {item.id}")

    data_asset = next(
        (a for a in item.assets if a.key in ("data", "visual", "default")),
        None,
    )
    if not data_asset:
        # Try first available asset
        data_asset = item.assets[0] if item.assets else None
    if not data_asset:
        print("No data asset found in tile.")
        return

    print(f"  Asset: {data_asset.key} -> {data_asset.href[:80]}...")

    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    print("Reading DEM tile...")
    with rasterio.open(data_asset.href) as src:
        crs_str = str(src.crs)
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *DENALI_BBOX)
        else:
            native_bounds = DENALI_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        elevation = src.read(1, window=window).astype(np.float32)
        nodata = src.nodata

    if nodata is not None:
        elevation[elevation == nodata] = np.nan

    print(f"  Shape: {elevation.shape}")
    print(f"  CRS: {crs_str}")
    print(f"  Elevation: {np.nanmin(elevation):.0f}m -- {np.nanmax(elevation):.0f}m")
    print(f"  Mean: {np.nanmean(elevation):.0f}m")

    # Compute hillshade
    print("Computing hillshade...")
    dy, dx = np.gradient(elevation)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)
    shade = np.clip(
        np.sin(np.radians(45)) * np.cos(slope)
        + np.cos(np.radians(45)) * np.sin(slope) * np.cos(np.radians(315) - aspect),
        0,
        1,
    )

    # Render
    print("Rendering...")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(14, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    ax_map, ax_hist = axes

    # Elevation map
    lons = np.linspace(DENALI_BBOX[0], DENALI_BBOX[2], elevation.shape[1])
    lats = np.linspace(DENALI_BBOX[3], DENALI_BBOX[1], elevation.shape[0])

    im = ax_map.imshow(
        elevation,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="viridis",
        aspect="auto",
    )
    ax_map.imshow(
        shade,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="gray",
        alpha=0.35,
        aspect="auto",
    )
    ax_map.set_title(
        f"Copernicus DEM 30m -- Denali / Alaska Range\nTile: {item.id}",
        fontsize=13,
        fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    # Histogram panel
    valid_elev = elevation[np.isfinite(elevation)]
    ax_hist.hist(
        valid_elev.ravel(),
        bins=60,
        color="#1f9e89",
        edgecolor="#31688e",
        alpha=0.85,
        orientation="horizontal",
    )
    ax_hist.set_ylabel("Elevation (m)", fontsize=10)
    ax_hist.set_xlabel("Pixel Count", fontsize=10)
    ax_hist.set_title("Elevation\nDistribution", fontsize=11)
    ax_hist.grid(True, alpha=0.3, axis="x")

    # Stats annotation on histogram
    stats_text = (
        f"Min:  {np.nanmin(elevation):>7.0f} m\n"
        f"Max:  {np.nanmax(elevation):>7.0f} m\n"
        f"Mean: {np.nanmean(elevation):>7.0f} m\n"
        f"Std:  {np.nanstd(elevation):>7.0f} m\n"
        f"Grid: {elevation.shape[1]}x{elevation.shape[0]}"
    )
    ax_hist.text(
        0.95,
        0.95,
        stats_text,
        transform=ax_hist.transAxes,
        fontsize=9,
        fontfamily="monospace",
        verticalalignment="top",
        horizontalalignment="right",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "alpha": 0.9},
    )

    fig.text(
        0.5,
        0.01,
        f"Data: Copernicus DEM GLO-30 via Earth Search | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center",
        fontsize=7,
        color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    elev_min = float(np.nanmin(elevation))
    elev_max = float(np.nanmax(elevation))
    relief = elev_max - elev_min
    sidecar = (
        f"Alt Text: Elevation map and histogram of the Denali / Alaska Range "
        f"from Copernicus DEM 30m via Earth Search STAC catalog. The map shows "
        f"terrain with viridis palette and hillshade overlay, elevations from "
        f"{elev_min:.0f}m to {elev_max:.0f}m ({relief:.0f}m relief). The "
        f"histogram shows elevation distribution, revealing the high-altitude "
        f"glaciated terrain of the Alaska Range.\n\n"
        f"Data Source: Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {STAC_API}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {DENALI_BBOX}\n"
        f"STAC Tile: {item.id}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/stac_copdem_alaska_demo.py\n"
        f"Parameters: collection=cop-dem-glo-30, bbox={DENALI_BBOX}\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
