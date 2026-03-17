"""OpenTopography DEM — Andes near Santiago, Chile.

Downloads a Copernicus 30m DEM of the Andes mountains near Santiago, Chile
from the OpenTopography API and generates an elevation map with hillshade
visualization and an east-west cross-section showing the dramatic rise
from the Central Valley to the Andean peaks.

Output: examples/outputs/opentopo_andes_santiago.png

Data source: Copernicus DEM 30m via OpenTopography API

Usage::

    python examples/scripts/opentopo_andes_demo.py
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

# Andes near Santiago, Chile — Central Valley to high Andes
ANDES_BBOX = {"south": -33.6, "north": -33.3, "west": -70.4, "east": -70.1}
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "opentopo_andes_santiago.png"
OUTPUT_TXT = OUTPUT_DIR / "opentopo_andes_santiago.txt"


async def main() -> None:
    """Download and visualize Andes DEM near Santiago, Chile."""
    print("EarthForge — OpenTopography Demo: Andes near Santiago, Chile")
    print("=" * 62)

    if not API_KEY:
        print("Error: Set OPENTOPO_API_KEY environment variable.")
        print("  Get a free key at: https://opentopography.org/developers")
        return

    import httpx

    params = {
        "demtype": "COP30",
        "south": ANDES_BBOX["south"],
        "north": ANDES_BBOX["north"],
        "west": ANDES_BBOX["west"],
        "east": ANDES_BBOX["east"],
        "outputFormat": "GTiff",
        "API_Key": API_KEY,
    }

    print("Requesting COP30 DEM from OpenTopography...")
    print("  Region: Andes near Santiago, Chile")
    print(f"  Bbox: {ANDES_BBOX}")

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
    print(f"  Relief: {np.nanmax(elevation) - np.nanmin(elevation):.0f}m")

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

    fig, axes = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [3, 1]})

    # Top: elevation map with hillshade
    ax_map = axes[0]
    lons = np.linspace(ANDES_BBOX["west"], ANDES_BBOX["east"], elevation.shape[1])
    lats = np.linspace(ANDES_BBOX["north"], ANDES_BBOX["south"], elevation.shape[0])

    im = ax_map.imshow(
        elevation,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="cividis", aspect="auto",
    )
    ax_map.imshow(
        shade, extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        cmap="gray", alpha=0.4, aspect="auto",
    )
    ax_map.set_title(
        "Copernicus DEM 30m — Andes near Santiago, Chile\n"
        "Central Valley to High Andes",
        fontsize=14, fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    # Draw cross-section line
    mid_row = elevation.shape[0] // 2
    ax_map.axhline(
        y=lats[mid_row], color="black", linewidth=3, linestyle="-", alpha=0.8,
    )
    ax_map.axhline(
        y=lats[mid_row], color="#ff6600", linewidth=1.5, linestyle="--", alpha=1.0,
    )
    ax_map.text(
        lons.min() + 0.005, lats[mid_row] + 0.01,
        "Cross-section", color="white", fontsize=9, fontweight="bold",
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "black", "alpha": 0.7},
    )

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Elevation (meters)", fontsize=11)

    # Bottom: east-west elevation cross-section
    ax_profile = axes[1]
    profile = elevation[mid_row, :]
    ax_profile.fill_between(lons, profile, alpha=0.6, color="#e1cc55")
    ax_profile.plot(lons, profile, color="#3b496c", linewidth=1)
    ax_profile.set_xlabel("Longitude", fontsize=10)
    ax_profile.set_ylabel("Elevation (m)", fontsize=10)
    ax_profile.set_title("E-W Elevation Cross-Section", fontsize=11)
    ax_profile.set_xlim(lons.min(), lons.max())
    ax_profile.grid(True, alpha=0.3)

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus DEM GLO-30 via OpenTopography API | "
        f"Palette: cividis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    Path(tmp_path).unlink(missing_ok=True)

    relief = band.max - band.min
    sidecar = (
        f"Alt Text: Elevation map and cross-section of the Andes near Santiago, "
        f"Chile from Copernicus DEM 30m data. Top panel shows terrain with "
        f"cividis palette and hillshade, elevations from {band.min:.0f}m "
        f"(Central Valley) to {band.max:.0f}m (Andean peaks), {relief:.0f}m of "
        f"relief. Bottom panel shows an east-west elevation profile capturing "
        f"the abrupt rise from valley to cordillera.\n\n"
        f"Data Source: ESA/Copernicus, Copernicus DEM GLO-30\n"
        f"URL: {OPENTOPO_API}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus DEM License\n"
        f"Spatial Extent: {ANDES_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/opentopo_andes_demo.py\n"
        f"Parameters: demtype=COP30, region=Andes/Santiago Chile\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
