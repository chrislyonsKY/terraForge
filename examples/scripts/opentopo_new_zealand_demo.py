"""OpenTopography DEM — Southern Alps, New Zealand (Mt. Cook / Aoraki).

Downloads a Copernicus 30m DEM of the Southern Alps near Mt. Cook / Aoraki
from the OpenTopography API and generates an elevation map with hillshade
visualization showing glaciated terrain and a statistics sidebar.

Output: examples/outputs/opentopo_new_zealand_alps.png

Data source: Copernicus DEM 30m via OpenTopography API

Usage::

    python examples/scripts/opentopo_new_zealand_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")


OPENTOPO_API = "https://portal.opentopography.org/API/globaldem"
API_KEY = os.environ.get("OPENTOPO_API_KEY", "")

# Southern Alps — Mt. Cook / Aoraki region, New Zealand
NZ_BBOX = {"south": -43.65, "north": -43.5, "west": 170.0, "east": 170.2}
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "opentopo_new_zealand_alps.png"
OUTPUT_TXT = OUTPUT_DIR / "opentopo_new_zealand_alps.txt"


async def main() -> None:
    """Download and visualize Southern Alps DEM from OpenTopography."""
    print("EarthForge — OpenTopography Demo: Southern Alps, New Zealand")
    print("=" * 62)

    if not API_KEY:
        print("Error: Set OPENTOPO_API_KEY environment variable.")
        print("  Get a free key at: https://opentopography.org/developers")
        return

    import httpx

    params = {
        "demtype": "COP30",
        "south": NZ_BBOX["south"],
        "north": NZ_BBOX["north"],
        "west": NZ_BBOX["west"],
        "east": NZ_BBOX["east"],
        "outputFormat": "GTiff",
        "API_Key": API_KEY,
    }

    print("Requesting COP30 DEM from OpenTopography...")
    print("  Region: Aoraki/Mt. Cook, Southern Alps, New Zealand")
    print(f"  Bbox: {NZ_BBOX}")

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(OPENTOPO_API, params=params)
        resp.raise_for_status()
        Path(tmp_path).write_bytes(resp.content)

    print(f"  Downloaded: {len(resp.content):,} bytes")

    import rasterio

    with rasterio.open(tmp_path) as src:
        elevation = src.read(1).astype(np.float32)
        crs_str = str(src.crs)
        nodata = src.nodata

    if nodata is not None:
        elevation[elevation == nodata] = np.nan

    print(f"  Shape: {elevation.shape}")
    print(f"  CRS: {crs_str}")
    print(f"  Elevation: {np.nanmin(elevation):.0f}m — {np.nanmax(elevation):.0f}m")
    print(f"  Mean: {np.nanmean(elevation):.0f}m")

    # Compute stats
    from earthforge.raster.stats import compute_stats

    stats = await compute_stats(tmp_path, histogram_bins=60)
    band = stats.bands[0]

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

    fig, (ax_map, ax_stats) = plt.subplots(
        1, 2, figsize=(13, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    lons = np.linspace(NZ_BBOX["west"], NZ_BBOX["east"], elevation.shape[1])
    lats = np.linspace(NZ_BBOX["north"], NZ_BBOX["south"], elevation.shape[0])

    im = ax_map.imshow(
        elevation,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="viridis", aspect="auto",
    )
    ax_map.imshow(
        shade, extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="gray", alpha=0.35, aspect="auto",
    )
    ax_map.set_title(
        "Copernicus DEM 30m — Southern Alps, New Zealand\n"
        "Aoraki / Mt. Cook Region",
        fontsize=13, fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    # Stats sidebar
    ax_stats.axis("off")
    stats_text = (
        f"Elevation Statistics\n"
        f"{'─' * 22}\n"
        f"Source:  OpenTopography\n"
        f"DEM:    Copernicus 30m\n"
        f"CRS:    {crs_str}\n"
        f"{'─' * 22}\n"
        f"Min:    {band.min:>8.0f} m\n"
        f"Max:    {band.max:>8.0f} m\n"
        f"Mean:   {band.mean:>8.0f} m\n"
        f"Median: {band.median:>8.0f} m\n"
        f"Std:    {band.std:>8.0f} m\n"
        f"{'─' * 22}\n"
        f"Pixels: {band.valid_pixels:>8,}\n"
        f"Grid:   {elevation.shape[1]}x{elevation.shape[0]}\n"
    )
    ax_stats.text(
        0.05, 0.95, stats_text,
        transform=ax_stats.transAxes,
        fontsize=10, fontfamily="monospace",
        verticalalignment="top",
    )

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus DEM GLO-30 via OpenTopography API | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    Path(tmp_path).unlink(missing_ok=True)

    sidecar = (
        f"Alt Text: Elevation map of the Southern Alps near Aoraki/Mt. Cook "
        f"in New Zealand from Copernicus DEM 30m data obtained via "
        f"OpenTopography API. Elevations range from {band.min:.0f}m (river "
        f"valleys) to {band.max:.0f}m (glaciated peaks), rendered with "
        f"viridis palette and NW-lit hillshade. Glacial valleys, aretes, and "
        f"cirques of the active alpine landscape are visible.\n\n"
        f"Data Source: ESA/Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {OPENTOPO_API}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {NZ_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/opentopo_new_zealand_demo.py\n"
        f"Parameters: demtype=COP30, region=Aoraki/Mt. Cook NZ\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
