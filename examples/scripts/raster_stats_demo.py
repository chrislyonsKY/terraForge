"""Raster statistics demo — elevation histogram from Copernicus DEM.

Generates a publication-quality histogram of elevation values from the
Copernicus DEM 30m dataset over Central Kentucky. Demonstrates the
`earthforge raster stats` module with real-world data.

Output: examples/outputs/raster_stats_dem_histogram.png

Data source: Copernicus DEM GLO-30 via Element84 Earth Search (public)

Usage::

    python examples/scripts/raster_stats_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
KY_BBOX = [-85.5, 37.0, -84.0, 38.5]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "raster_stats_dem_histogram.png"
OUTPUT_TXT = OUTPUT_DIR / "raster_stats_dem_histogram.txt"


async def main() -> None:
    """Generate DEM elevation histogram."""
    print("EarthForge — Raster Stats Demo: Copernicus DEM Histogram")
    print("=" * 60)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Search for DEM tiles
    print("Searching for Copernicus DEM tiles over Kentucky...")
    result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=KY_BBOX,
        max_items=5,
    )

    if not result.items:
        print("No DEM tiles found. Check network connectivity.")
        return

    item = result.items[0]
    print(f"Using item: {item.id}")

    # Find the data asset
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

    # Generate histogram plot
    print("Generating histogram...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, (ax_hist, ax_stats) = plt.subplots(
        1, 2, figsize=(12, 6),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    # Histogram with viridis-derived bar colors
    edges = band.histogram_edges
    counts = band.histogram_counts
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(counts))]
    widths = [edges[i + 1] - edges[i] for i in range(len(counts))]

    # Color bars by elevation value (viridis)
    rng = band.max - band.min if band.max > band.min else 1
    norm_vals = [(c - band.min) / rng for c in centers]
    cmap = plt.cm.viridis
    colors = [cmap(v) for v in norm_vals]

    ax_hist.bar(centers, counts, width=widths, color=colors, edgecolor="none", alpha=0.9)
    ax_hist.set_xlabel("Elevation (meters)", fontsize=11)
    ax_hist.set_ylabel("Pixel Count", fontsize=11)
    ax_hist.set_title(
        f"Copernicus DEM 30m — Elevation Distribution\n"
        f"Central Kentucky ({KY_BBOX[0]}W, {KY_BBOX[1]}S, {KY_BBOX[2]}E, {KY_BBOX[3]}N)",
        fontsize=12, fontweight="bold",
    )
    ax_hist.tick_params(labelsize=10)

    # Stats sidebar
    ax_stats.axis("off")
    stats_text = (
        f"Summary Statistics\n"
        f"{'─' * 22}\n"
        f"Min:      {band.min:>8.1f} m\n"
        f"Max:      {band.max:>8.1f} m\n"
        f"Mean:     {band.mean:>8.1f} m\n"
        f"Median:   {band.median:>8.1f} m\n"
        f"Std Dev:  {band.std:>8.1f} m\n"
        f"{'─' * 22}\n"
        f"Pixels:   {band.valid_pixels:>8,}\n"
        f"Nodata:   {band.nodata_pixels:>8,}\n"
        f"Size:     {stats_result.width}x{stats_result.height}\n"
        f"CRS:      {stats_result.crs or 'N/A'}\n"
    )
    ax_stats.text(
        0.1, 0.95, stats_text,
        transform=ax_stats.transAxes,
        fontsize=10, fontfamily="monospace",
        verticalalignment="top",
    )

    # Attribution
    fig.text(
        0.5, 0.01,
        f"Data: Copernicus DEM GLO-30 via Earth Search | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=8, color="gray",
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    # Write sidecar
    sidecar = (
        f"Alt Text: Histogram showing elevation distribution of Copernicus DEM 30m data "
        f"over Central Kentucky. Elevations range from {band.min:.0f}m to {band.max:.0f}m "
        f"with a mean of {band.mean:.0f}m. Bars are colored using the viridis palette.\n\n"
        f"Data Source: Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {data_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {KY_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/raster_stats_demo.py\n"
        f"Parameters: collection=cop-dem-glo-30, bbox={KY_BBOX}, bins=80\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
