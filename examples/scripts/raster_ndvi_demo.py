"""NDVI map from Sentinel-2 — colorblind-safe diverging palette.

Generates a publication-quality NDVI map of Central Kentucky from
Sentinel-2 Level-2A data. Uses the brown-white-teal (BrBG) diverging
palette from earthforge.core.palettes for colorblind safety.

Output: examples/outputs/raster_ndvi_kentucky.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/raster_ndvi_demo.py
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
from earthforge.core.palettes import DIVERGING_BRBG
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
KY_BBOX = [-84.6, 37.8, -84.3, 38.1]  # Smaller window for faster download
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "raster_ndvi_kentucky.png"
OUTPUT_TXT = OUTPUT_DIR / "raster_ndvi_kentucky.txt"


async def main() -> None:
    """Generate NDVI map from Sentinel-2."""
    print("EarthForge — NDVI Demo: Sentinel-2 Kentucky")
    print("=" * 55)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Search for clear scenes
    print("Searching for clear Sentinel-2 scenes...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=KY_BBOX,
        datetime_range="2025-06-01/2025-09-30",
        max_items=20,
    )

    # Pick clearest scene
    candidates = [
        item for item in result.items if (item.properties.get("eo:cloud_cover") or 100) < 15
    ]
    if not candidates:
        print("No clear scenes found. Try a wider date range.")
        return

    candidates.sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
    item = candidates[0]
    cc = item.properties.get("eo:cloud_cover", "?")
    print(f"Selected: {item.id} (cloud: {cc}%)")

    # Get band URLs
    red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
    nir_asset = next((a for a in item.assets if a.key in ("nir", "B08")), None)
    if not red_asset or not nir_asset:
        print("Missing red/NIR bands.")
        return

    # Read windows
    print("Reading Red band (B04)...")
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(red_asset.href) as src:
        crs_str = str(src.crs)
        # Reproject bbox from WGS84 to the raster's CRS
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *KY_BBOX)
        else:
            native_bounds = KY_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)
        print(f"  Red shape: {red.shape}, CRS: {crs_str}")

    print("Reading NIR band (B08)...")
    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *KY_BBOX)
        else:
            native_bounds = KY_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        nir = src.read(1, window=window).astype(np.float32)
        print(f"  NIR shape: {nir.shape}")

    # Match shapes
    min_h = min(red.shape[0], nir.shape[0])
    min_w = min(red.shape[1], nir.shape[1])
    red = red[:min_h, :min_w]
    nir = nir[:min_h, :min_w]

    # Compute NDVI
    print("Computing NDVI...")
    denom = nir + red
    ndvi = np.where(denom > 0, (nir - red) / denom, 0)
    ndvi = np.clip(ndvi, -1, 1)
    print(f"  NDVI range: [{ndvi.min():.3f}, {ndvi.max():.3f}]")
    print(f"  Mean NDVI: {ndvi.mean():.3f}")

    # Render with BrBG palette
    print("Rendering map...")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    # Create colormap from BrBG palette
    brbg_colors = [tuple(int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)) for h in DIVERGING_BRBG]
    cmap = LinearSegmentedColormap.from_list("brbg", brbg_colors, N=256)

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(ndvi, cmap=cmap, vmin=-0.5, vmax=1.0, aspect="auto")

    ax.set_title(
        f"NDVI — Sentinel-2 L2A\nCentral Kentucky | {(item.datetime or 'Unknown')[:10]}",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel(f"Pixels (CRS: {crs_str})", fontsize=10)
    ax.set_ylabel("Pixels", fontsize=10)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)
    cbar.ax.tick_params(labelsize=9)

    # Attribution
    fig.text(
        0.5,
        0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center",
        fontsize=7,
        color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    # Sidecar
    sidecar = (
        f"Alt Text: NDVI map of Central Kentucky from Sentinel-2 imagery dated "
        f"{(item.datetime or 'Unknown')[:10]}. Vegetation density is shown using a "
        f"brown-white-teal diverging palette (BrBG). Brown indicates bare soil/low "
        f"vegetation, white indicates moderate NDVI (~0.25), and teal indicates "
        f"dense vegetation (NDVI > 0.5). Mean NDVI: {ndvi.mean():.3f}.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {KY_BBOX}\n"
        f"Temporal Extent: {(item.datetime or 'Unknown')[:10]}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/raster_ndvi_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={KY_BBOX}, "
        f"cloud_cover<15%, palette=BrBG\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
