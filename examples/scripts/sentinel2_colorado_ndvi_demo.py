"""Sentinel-2 NDVI — Colorado Rocky Mountain Front Range.

Computes NDVI from Sentinel-2 over the Colorado Front Range, showing
the elevation-driven vegetation gradient from plains to alpine tundra.

Output: examples/outputs/ndvi_colorado_front_range.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/sentinel2_colorado_ndvi_demo.py
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
# Colorado Front Range — Boulder to Rocky Mountain NP
CO_BBOX = [-105.7, 39.9, -105.3, 40.15]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "ndvi_colorado_front_range.png"
OUTPUT_TXT = OUTPUT_DIR / "ndvi_colorado_front_range.txt"


async def main() -> None:
    """Generate NDVI map of Colorado Front Range."""
    print("EarthForge — NDVI Demo: Colorado Front Range")
    print("=" * 50)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for clear Sentinel-2 scenes over Colorado...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=CO_BBOX,
        datetime_range="2025-07-01/2025-09-15",
        max_items=20,
    )

    candidates = [
        item for item in result.items
        if (item.properties.get("eo:cloud_cover") or 100) < 15
    ]
    if not candidates:
        print("No clear scenes found.")
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
            native_bounds = transform_bounds("EPSG:4326", src.crs, *CO_BBOX)
        else:
            native_bounds = CO_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)

    print("Reading NIR band...")
    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *CO_BBOX)
        else:
            native_bounds = CO_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        nir = src.read(1, window=window).astype(np.float32)

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
        print("matplotlib required")
        return

    brbg_colors = [
        tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
        for h in DIVERGING_BRBG
    ]
    cmap = LinearSegmentedColormap.from_list("brbg", brbg_colors, N=256)

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(ndvi, cmap=cmap, vmin=-0.3, vmax=0.9, aspect="auto")

    ax.set_title(
        f"NDVI — Colorado Front Range\n"
        f"Sentinel-2 | {(item.datetime or 'Unknown')[:10]} | {crs_str}",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlabel("Pixels (east-west)", fontsize=10)
    ax.set_ylabel("Pixels (north-south)", fontsize=10)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | Boulder to RMNP | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: NDVI map of the Colorado Front Range (Boulder to Rocky "
        f"Mountain National Park) from Sentinel-2 data dated "
        f"{(item.datetime or 'Unknown')[:10]}. Shows the vegetation gradient "
        f"from urban/agricultural plains (low NDVI, brown) through montane "
        f"forest (high NDVI, teal) to alpine tundra. BrBG diverging palette.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {CO_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/sentinel2_colorado_ndvi_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={CO_BBOX}\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
