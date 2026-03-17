"""Sentinel-2 NDVI -- Amazon tropical forest near Manaus, Brazil.

Computes NDVI from Sentinel-2 over the Amazon rainforest near Manaus,
showing dense tropical canopy with characteristically high NDVI values
contrasted against river channels.

Output: examples/outputs/ndvi_amazon_manaus.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/sentinel2_amazon_ndvi_demo.py
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
from earthforge.core.palettes import DIVERGING_BRBG
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
# Amazon rainforest near Manaus, Brazil
AMAZON_BBOX = [-60.5, -3.5, -60.0, -3.0]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "ndvi_amazon_manaus.png"
OUTPUT_TXT = OUTPUT_DIR / "ndvi_amazon_manaus.txt"


async def main() -> None:
    """Generate NDVI map of Amazon forest near Manaus."""
    print("EarthForge -- NDVI Demo: Amazon Rainforest (Manaus)")
    print("=" * 55)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for clear Sentinel-2 scenes over the Amazon...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=AMAZON_BBOX,
        datetime_range="2025-06-01/2025-10-31",
        max_items=25,
    )

    candidates = [
        item for item in result.items
        if (item.properties.get("eo:cloud_cover") or 100) < 20
    ]
    if not candidates:
        print("No clear scenes found. Tropical cloud cover is persistent.")
        return

    candidates.sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
    item = candidates[0]
    cc = item.properties.get("eo:cloud_cover", "?")
    print(f"Selected: {item.id} (cloud: {cc}%)")

    red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
    nir_asset = next((a for a in item.assets if a.key in ("nir", "B08")), None)
    if not red_asset or not nir_asset:
        print("Missing red/NIR bands.")
        return

    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    print("Reading Red band...")
    with rasterio.open(red_asset.href) as src:
        crs_str = str(src.crs)
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *AMAZON_BBOX)
        else:
            native_bounds = AMAZON_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)

    print("Reading NIR band...")
    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *AMAZON_BBOX)
        else:
            native_bounds = AMAZON_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        nir = src.read(1, window=window).astype(np.float32)

    # Align shapes
    min_h = min(red.shape[0], nir.shape[0])
    min_w = min(red.shape[1], nir.shape[1])
    red, nir = red[:min_h, :min_w], nir[:min_h, :min_w]

    denom = nir + red
    ndvi = np.where(denom > 0, (nir - red) / denom, 0)
    ndvi = np.clip(ndvi, -1, 1)
    print(f"NDVI range: [{ndvi.min():.3f}, {ndvi.max():.3f}], mean: {ndvi.mean():.3f}")

    # Render
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    brbg_colors = [
        tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
        for h in DIVERGING_BRBG
    ]
    cmap = LinearSegmentedColormap.from_list("brbg", brbg_colors, N=256)

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(ndvi, cmap=cmap, vmin=-0.3, vmax=0.9, aspect="auto")

    ax.set_title(
        f"NDVI -- Amazon Rainforest (Manaus, Brazil)\n"
        f"Sentinel-2 | {(item.datetime or 'Unknown')[:10]} | {crs_str}",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlabel("Pixels (east-west)", fontsize=10)
    ax.set_ylabel("Pixels (north-south)", fontsize=10)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)

    # Add NDVI class annotations
    ax.text(
        0.02, 0.02,
        f"Dense canopy (NDVI > 0.7): {np.sum(ndvi > 0.7) / ndvi.size * 100:.1f}%\n"
        f"Water/bare (NDVI < 0.1): {np.sum(ndvi < 0.1) / ndvi.size * 100:.1f}%",
        transform=ax.transAxes, fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
    )

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | Manaus, Brazil | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    dense_pct = np.sum(ndvi > 0.7) / ndvi.size * 100
    sidecar = (
        f"Alt Text: NDVI map of the Amazon rainforest near Manaus, Brazil from "
        f"Sentinel-2 data dated {(item.datetime or 'Unknown')[:10]}. Dense tropical "
        f"canopy dominates with high NDVI values (teal, > 0.7 covering {dense_pct:.1f}% "
        f"of pixels). River channels and clearings appear as low-NDVI areas (brown). "
        f"BrBG diverging palette.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {AMAZON_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/sentinel2_amazon_ndvi_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={AMAZON_BBOX}\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
