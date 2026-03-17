"""DEM preview with hillshade — Copernicus DEM over Eastern Kentucky.

Generates a preview image from the Copernicus DEM 30m showing elevation
with a hillshade overlay for terrain visualization. Uses the viridis
palette from earthforge.core.palettes for colorblind safety.

Output: examples/outputs/raster_preview_dem_ky.png

Data source: Copernicus DEM GLO-30 via Element84 Earth Search (public)

Usage::

    python examples/scripts/raster_preview_dem_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.core.palettes import VIRIDIS
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
EAST_KY_BBOX = [-83.8, 37.4, -83.2, 37.9]  # Eastern KY — Appalachian foothills
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "raster_preview_dem_ky.png"
OUTPUT_TXT = OUTPUT_DIR / "raster_preview_dem_ky.txt"


def compute_hillshade(
    elevation: np.ndarray,
    azimuth: float = 315.0,
    altitude: float = 45.0,
) -> np.ndarray:
    """Compute hillshade from an elevation array.

    Parameters:
        elevation: 2D array of elevation values.
        azimuth: Sun azimuth in degrees (default: 315 = NW).
        altitude: Sun altitude in degrees (default: 45).

    Returns:
        2D array of hillshade values (0-255).
    """
    az_rad = np.radians(azimuth)
    alt_rad = np.radians(altitude)

    dy, dx = np.gradient(elevation)
    slope = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)

    shade = (
        np.sin(alt_rad) * np.cos(slope)
        + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect)
    )
    shade = np.clip(shade, 0, 1)
    return (shade * 255).astype(np.uint8)


async def main() -> None:
    """Generate DEM preview with hillshade."""
    print("EarthForge — DEM Preview: Eastern Kentucky Hillshade")
    print("=" * 55)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for Copernicus DEM tiles...")
    result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=EAST_KY_BBOX,
        max_items=5,
    )

    if not result.items:
        print("No DEM tiles found.")
        return

    item = result.items[0]
    data_asset = next((a for a in item.assets if a.key == "data"), None)
    if not data_asset:
        print("No data asset found.")
        return

    print(f"Reading DEM: {item.id}")
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(data_asset.href) as src:
        window = from_bounds(*EAST_KY_BBOX, transform=src.transform)
        elevation = src.read(1, window=window).astype(np.float32)
        crs_str = str(src.crs)

    print(f"  Shape: {elevation.shape}")
    print(f"  Elevation range: {elevation.min():.0f}m — {elevation.max():.0f}m")

    # Compute hillshade
    print("Computing hillshade...")
    shade = compute_hillshade(elevation)

    # Render
    print("Rendering...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    # Elevation with viridis
    im = ax.imshow(elevation, cmap="viridis", aspect="auto")

    # Hillshade overlay
    ax.imshow(shade, cmap="gray", alpha=0.35, aspect="auto")

    ax.set_title(
        f"Copernicus DEM 30m — Eastern Kentucky\n"
        f"Elevation with Hillshade Overlay",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlabel(f"Pixels (CRS: {crs_str})", fontsize=10)
    ax.set_ylabel("Pixels", fontsize=10)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus DEM GLO-30 via Earth Search | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: Elevation map of Eastern Kentucky from the Copernicus DEM 30m "
        f"dataset with hillshade overlay. The Appalachian foothills show elevations "
        f"ranging from {elevation.min():.0f}m to {elevation.max():.0f}m, rendered "
        f"with the viridis colorblind-safe palette and northwest-lit hillshade.\n\n"
        f"Data Source: Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {data_asset.href}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {EAST_KY_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/raster_preview_dem_demo.py\n"
        f"Parameters: collection=cop-dem-glo-30, bbox={EAST_KY_BBOX}, "
        f"hillshade_azimuth=315, hillshade_altitude=45\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
