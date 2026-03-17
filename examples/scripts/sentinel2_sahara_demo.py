"""Sentinel-2 NDVI -- Sahara Desert, Algeria.

Computes NDVI from Sentinel-2 over the central Sahara Desert in Algeria,
demonstrating extremely low NDVI values characteristic of hyperarid
landscapes where virtually no photosynthetic vegetation exists.

Output: examples/outputs/ndvi_sahara_algeria.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/sentinel2_sahara_demo.py
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
# Central Sahara Desert, Algeria
SAHARA_BBOX = [2.0, 24.0, 3.0, 25.0]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "ndvi_sahara_algeria.png"
OUTPUT_TXT = OUTPUT_DIR / "ndvi_sahara_algeria.txt"


async def main() -> None:
    """Generate NDVI map of the Sahara Desert."""
    print("EarthForge -- NDVI Demo: Sahara Desert (Algeria)")
    print("=" * 53)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for clear Sentinel-2 scenes over the Sahara...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=SAHARA_BBOX,
        datetime_range="2025-01-01/2025-12-31",
        max_items=20,
    )

    # Desert has reliably low cloud cover
    candidates = [
        item for item in result.items
        if (item.properties.get("eo:cloud_cover") or 100) < 10
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
            native_bounds = transform_bounds("EPSG:4326", src.crs, *SAHARA_BBOX)
        else:
            native_bounds = SAHARA_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)

    print("Reading NIR band...")
    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *SAHARA_BBOX)
        else:
            native_bounds = SAHARA_BBOX
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

    fig, (ax_map, ax_hist) = plt.subplots(
        1, 2, figsize=(13, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    im = ax_map.imshow(ndvi, cmap=cmap, vmin=-0.3, vmax=0.9, aspect="auto")

    ax_map.set_title(
        f"NDVI -- Sahara Desert (Algeria)\n"
        f"Sentinel-2 | {(item.datetime or 'Unknown')[:10]} | {crs_str}",
        fontsize=13, fontweight="bold",
    )
    ax_map.set_xlabel("Pixels (east-west)", fontsize=10)
    ax_map.set_ylabel("Pixels (north-south)", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)

    # NDVI histogram showing desert distribution
    valid_ndvi = ndvi[np.isfinite(ndvi)]
    ax_hist.hist(
        valid_ndvi.ravel(), bins=60, color="#bf812d", edgecolor="#8c510a",
        alpha=0.8, orientation="horizontal",
    )
    ax_hist.set_ylabel("NDVI", fontsize=10)
    ax_hist.set_xlabel("Pixel Count", fontsize=10)
    ax_hist.set_title("NDVI Distribution", fontsize=11)
    ax_hist.set_ylim(-0.3, 0.9)
    ax_hist.axhline(y=0.1, color="gray", linestyle="--", alpha=0.5, linewidth=0.8)
    ax_hist.text(
        0.95, 0.12, "Vegetation threshold",
        transform=ax_hist.get_yaxis_transform(),
        fontsize=8, color="gray", ha="right",
    )
    ax_hist.grid(True, alpha=0.3, axis="x")

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | Sahara, Algeria | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    bare_pct = np.sum(ndvi < 0.1) / ndvi.size * 100
    sidecar = (
        f"Alt Text: NDVI map of the Sahara Desert in Algeria from Sentinel-2 "
        f"data dated {(item.datetime or 'Unknown')[:10]}. The scene is dominated "
        f"by extremely low NDVI values (brown tones), with {bare_pct:.1f}% of "
        f"pixels below 0.1, confirming hyperarid conditions with no detectable "
        f"photosynthetic vegetation. A histogram sidebar shows the tight NDVI "
        f"distribution clustered near zero. BrBG diverging palette.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {SAHARA_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/sentinel2_sahara_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={SAHARA_BBOX}\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
