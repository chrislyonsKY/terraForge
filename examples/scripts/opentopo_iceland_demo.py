"""OpenTopography DEM -- Iceland Vatnajokull glacier terrain.

Downloads a Copernicus 30m DEM of the Vatnajokull glacier area in
southeast Iceland from the OpenTopography API and renders glacial
terrain with the cividis palette.

Output: examples/outputs/opentopo_iceland_glacier.png

Data source: Copernicus DEM 30m via OpenTopography API

Usage::

    python examples/scripts/opentopo_iceland_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")

from earthforge.core.palettes import CIVIDIS

OPENTOPO_API = "https://portal.opentopography.org/API/globaldem"
API_KEY = os.environ.get("OPENTOPO_API_KEY", "")

# Vatnajokull glacier area, Iceland
ICE_BBOX = {"south": 64.3, "north": 64.5, "west": -16.8, "east": -16.4}
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "opentopo_iceland_glacier.png"
OUTPUT_TXT = OUTPUT_DIR / "opentopo_iceland_glacier.txt"


async def main() -> None:
    """Download and visualize Iceland Vatnajokull DEM from OpenTopography."""
    print("EarthForge -- OpenTopography Demo: Iceland (Vatnajokull)")
    print("=" * 58)

    if not API_KEY:
        print("Error: Set OPENTOPO_API_KEY environment variable.")
        print("  Get a free key at: https://opentopography.org/developers")
        return

    import httpx

    params = {
        "demtype": "COP30",
        "south": ICE_BBOX["south"],
        "north": ICE_BBOX["north"],
        "west": ICE_BBOX["west"],
        "east": ICE_BBOX["east"],
        "outputFormat": "GTiff",
        "API_Key": API_KEY,
    }

    print("Requesting COP30 DEM from OpenTopography...")
    print(f"  Region: Vatnajokull Glacier, Iceland")
    print(f"  Bbox: {ICE_BBOX}")

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(OPENTOPO_API, params=params)
        resp.raise_for_status()
        Path(tmp_path).write_bytes(resp.content)

    print(f"  Downloaded: {len(resp.content):,} bytes")

    # Read and analyze
    import rasterio

    with rasterio.open(tmp_path) as src:
        elevation = src.read(1).astype(np.float32)
        crs_str = str(src.crs)
        nodata = src.nodata

    if nodata is not None:
        elevation[elevation == nodata] = np.nan

    print(f"  Shape: {elevation.shape}")
    print(f"  CRS: {crs_str}")
    print(f"  Elevation: {np.nanmin(elevation):.0f}m -- {np.nanmax(elevation):.0f}m")
    print(f"  Mean: {np.nanmean(elevation):.0f}m")

    # Compute stats
    from earthforge.raster.stats import compute_stats

    stats = await compute_stats(tmp_path, histogram_bins=60)
    band = stats.bands[0]

    # Compute hillshade
    print("Computing hillshade...")
    dy, dx = np.gradient(elevation)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    az_rad = np.radians(315)
    alt_rad = np.radians(45)
    aspect = np.arctan2(-dy, dx)
    shade = (
        np.sin(alt_rad) * np.cos(slope)
        + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect)
    )
    shade = np.clip(shade, 0, 1)

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

    lons = np.linspace(ICE_BBOX["west"], ICE_BBOX["east"], elevation.shape[1])
    lats = np.linspace(ICE_BBOX["north"], ICE_BBOX["south"], elevation.shape[0])

    im = ax_map.imshow(
        elevation,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="cividis", aspect="auto",
    )
    ax_map.imshow(
        shade, extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="gray", alpha=0.35, aspect="auto",
    )
    ax_map.set_title(
        "Copernicus DEM 30m -- Iceland\n"
        "Vatnajokull Glacier Region",
        fontsize=13, fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    # Stats sidebar
    ax_stats.axis("off")
    relief = band.max - band.min
    stats_text = (
        f"Elevation Statistics\n"
        f"{'---' * 8}\n"
        f"Source:  OpenTopography\n"
        f"DEM:    Copernicus 30m\n"
        f"CRS:    {crs_str}\n"
        f"{'---' * 8}\n"
        f"Min:    {band.min:>8.0f} m\n"
        f"Max:    {band.max:>8.0f} m\n"
        f"Mean:   {band.mean:>8.0f} m\n"
        f"Median: {band.median:>8.0f} m\n"
        f"Std:    {band.std:>8.0f} m\n"
        f"Relief: {relief:>8.0f} m\n"
        f"{'---' * 8}\n"
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
        f"Palette: cividis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    # Cleanup
    Path(tmp_path).unlink(missing_ok=True)

    sidecar = (
        f"Alt Text: Elevation map of the Vatnajokull glacier region in Iceland "
        f"from Copernicus DEM 30m data obtained via OpenTopography API. "
        f"Elevations range from {band.min:.0f}m (coastal lowlands and glacial "
        f"outwash plains) to {band.max:.0f}m (glacier ice cap), rendered with "
        f"cividis palette and NW-lit hillshade. Glacial valleys, outlet glaciers, "
        f"and the flat ice cap surface are visible.\n\n"
        f"Data Source: Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {OPENTOPO_API}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {ICE_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/opentopo_iceland_demo.py\n"
        f"Parameters: demtype=COP30, region=Vatnajokull Iceland\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
