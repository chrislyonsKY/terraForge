"""STAC Copernicus DEM — Great Smoky Mountains, Appalachian terrain.

Searches for Copernicus DEM 30m tiles over the Great Smoky Mountains
via STAC, reads the DEM data, computes elevation statistics, and renders
a histogram and elevation map of the ancient Appalachian terrain.

Output: examples/outputs/dem_stats_great_smokies.png

Data source: Copernicus DEM GLO-30 via Element84 Earth Search (public)

Usage::

    python examples/scripts/stac_copdem_appalachian_demo.py
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
# Great Smoky Mountains — NC/TN border
SMOKIES_BBOX = [-83.8, 35.4, -83.2, 35.8]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "dem_stats_great_smokies.png"
OUTPUT_TXT = OUTPUT_DIR / "dem_stats_great_smokies.txt"


async def main() -> None:
    """Generate DEM statistics and visualization for Great Smoky Mountains."""
    print("EarthForge — STAC DEM Demo: Great Smoky Mountains, Appalachians")
    print("=" * 64)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for Copernicus DEM tiles over Great Smoky Mountains...")
    result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=SMOKIES_BBOX,
        max_items=5,
    )

    if not result.items:
        print("No DEM tiles found. Check network connectivity.")
        return

    item = result.items[0]
    print(f"Using item: {item.id}")

    data_asset = next((a for a in item.assets if a.key == "data"), None)
    if not data_asset:
        print("No 'data' asset found on item.")
        return

    print(f"Asset URL: {data_asset.href}")

    # Compute stats
    print("Computing raster statistics...")
    from earthforge.raster.stats import compute_stats

    stats_result = await compute_stats(data_asset.href, histogram_bins=80)
    band = stats_result.bands[0]

    print(f"  Min: {band.min:.1f} m")
    print(f"  Max: {band.max:.1f} m")
    print(f"  Mean: {band.mean:.1f} m")
    print(f"  Std: {band.std:.1f} m")
    print(f"  Median: {band.median:.1f} m")
    print(f"  Valid pixels: {band.valid_pixels:,}")

    # Read elevation for map panel
    print("Reading elevation data for visualization...")
    import rasterio

    with rasterio.open(data_asset.href) as src:
        elevation = src.read(1).astype(np.float32)
        crs_str = str(src.crs)
        nodata = src.nodata
        bounds = src.bounds

    if nodata is not None:
        elevation[elevation == nodata] = np.nan

    # Hillshade
    print("Computing hillshade...")
    dy, dx = np.gradient(elevation)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    az_rad = np.radians(315)
    alt_rad = np.radians(45)
    aspect = np.arctan2(-dy, dx)
    shade = np.clip(
        np.sin(alt_rad) * np.cos(slope)
        + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect),
        0, 1,
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

    fig, ((ax_map, ax_stats_panel), (ax_hist, ax_blank)) = plt.subplots(
        2, 2, figsize=(14, 10),
        gridspec_kw={"width_ratios": [3, 1], "height_ratios": [3, 2]},
    )

    # Top-left: elevation map with hillshade
    im = ax_map.imshow(
        elevation,
        extent=[bounds.left, bounds.right, bounds.bottom, bounds.top],
        cmap="viridis", aspect="auto",
    )
    ax_map.imshow(
        shade,
        extent=[bounds.left, bounds.right, bounds.bottom, bounds.top],
        cmap="gray", alpha=0.35, aspect="auto",
    )
    ax_map.set_title(
        "Copernicus DEM 30m — Great Smoky Mountains\n"
        "Southern Appalachian Highlands, NC/TN",
        fontsize=13, fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    # Top-right: statistics panel
    ax_stats_panel.axis("off")
    stats_text = (
        f"Elevation Statistics\n"
        f"{'─' * 22}\n"
        f"Source:  Earth Search\n"
        f"DEM:    COP-DEM-GLO-30\n"
        f"CRS:    {crs_str}\n"
        f"{'─' * 22}\n"
        f"Min:    {band.min:>8.0f} m\n"
        f"Max:    {band.max:>8.0f} m\n"
        f"Mean:   {band.mean:>8.0f} m\n"
        f"Median: {band.median:>8.0f} m\n"
        f"Std:    {band.std:>8.0f} m\n"
        f"{'─' * 22}\n"
        f"Relief: {band.max - band.min:>8.0f} m\n"
        f"Pixels: {band.valid_pixels:>8,}\n"
        f"Size:   {stats_result.width}x{stats_result.height}\n"
    )
    ax_stats_panel.text(
        0.05, 0.95, stats_text,
        transform=ax_stats_panel.transAxes,
        fontsize=10, fontfamily="monospace",
        verticalalignment="top",
    )

    # Bottom-left: histogram
    edges = band.histogram_edges
    counts = band.histogram_counts
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(counts))]
    widths = [edges[i + 1] - edges[i] for i in range(len(counts))]

    norm_vals = [
        (c - band.min) / (band.max - band.min) if band.max > band.min else 0.5
        for c in centers
    ]
    bar_cmap = plt.cm.viridis
    colors = [bar_cmap(v) for v in norm_vals]

    ax_hist.bar(centers, counts, width=widths, color=colors, edgecolor="none", alpha=0.9)
    ax_hist.set_xlabel("Elevation (meters)", fontsize=10)
    ax_hist.set_ylabel("Pixel Count", fontsize=10)
    ax_hist.set_title("Elevation Distribution", fontsize=11, fontweight="bold")
    ax_hist.tick_params(labelsize=9)

    # Bottom-right: blank
    ax_blank.axis("off")

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus DEM GLO-30 via Earth Search | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: Elevation map and histogram of the Great Smoky Mountains "
        f"from Copernicus DEM 30m data via STAC. Top panel shows the ancient "
        f"Appalachian terrain with viridis palette and hillshade. Elevations "
        f"range from {band.min:.0f}m to {band.max:.0f}m with "
        f"{band.max - band.min:.0f}m of relief. Bottom panel shows the "
        f"elevation distribution. The rounded ridgelines characteristic of "
        f"the old Appalachian orogeny are visible.\n\n"
        f"Data Source: Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {data_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {SMOKIES_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/stac_copdem_appalachian_demo.py\n"
        f"Parameters: collection=cop-dem-glo-30, bbox={SMOKIES_BBOX}\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
