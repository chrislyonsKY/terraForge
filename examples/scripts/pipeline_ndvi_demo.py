"""Pipeline NDVI demo — real STAC to NDVI workflow.

Demonstrates the earthforge pipeline runner executing a real
STAC search -> band math -> COG output workflow using Sentinel-2 data.

Output: examples/outputs/pipeline_ndvi_output.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/pipeline_ndvi_demo.py
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
sys.path.insert(0, "packages/pipeline/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.core.palettes import DIVERGING_BRBG
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
KY_BBOX = [-84.55, 38.00, -84.45, 38.08]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "pipeline_ndvi_output.png"
OUTPUT_TXT = OUTPUT_DIR / "pipeline_ndvi_output.txt"


async def main() -> None:
    """Run real STAC to NDVI pipeline."""
    print("EarthForge — Pipeline Demo: STAC -> NDVI")
    print("=" * 45)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Step 1: STAC search
    print("Step 1: Searching for clear Sentinel-2 scene...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=KY_BBOX,
        datetime_range="2025-06-01/2025-09-30",
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
    print(f"  Selected: {item.id} (cloud: {cc}%)")

    # Step 2: Read bands
    red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
    nir_asset = next((a for a in item.assets if a.key in ("nir", "B08")), None)
    if not red_asset or not nir_asset:
        print("Missing red/NIR bands.")
        return

    print("Step 2: Reading bands via range requests...")
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(red_asset.href) as src:
        crs_str = str(src.crs)
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *KY_BBOX)
        else:
            native_bounds = KY_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)
        print(f"  Red (B04): {red.shape}, CRS: {crs_str}")

    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *KY_BBOX)
        else:
            native_bounds = KY_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        nir = src.read(1, window=window).astype(np.float32)
        print(f"  NIR (B08): {nir.shape}")

    min_h = min(red.shape[0], nir.shape[0])
    min_w = min(red.shape[1], nir.shape[1])
    red, nir = red[:min_h, :min_w], nir[:min_h, :min_w]

    # Step 3: Compute NDVI using expression evaluator
    print("Step 3: Computing NDVI...")
    from earthforge.core.expression import safe_eval

    ndvi = safe_eval("(B08 - B04) / (B08 + B04)", {
        "B08": np.where(nir + red > 0, nir, 0.0),
        "B04": np.where(nir + red > 0, red, 0.0),
    })
    # Handle division-by-zero
    ndvi = np.where(np.isfinite(ndvi), ndvi, 0)
    ndvi = np.clip(ndvi, -1, 1)
    print(f"  NDVI range: [{ndvi.min():.3f}, {ndvi.max():.3f}]")
    print(f"  Mean NDVI: {ndvi.mean():.3f}")

    # Step 4: Render
    print("Step 4: Rendering output...")
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

    fig, (ax_ndvi, ax_summary) = plt.subplots(
        1, 2, figsize=(13, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    im = ax_ndvi.imshow(ndvi, cmap=cmap, vmin=-0.5, vmax=1.0, aspect="auto")
    ax_ndvi.set_title(
        f"NDVI — Pipeline Output\n"
        f"{(item.datetime or 'Unknown')[:10]} | {crs_str}",
        fontsize=13, fontweight="bold",
    )
    cbar = fig.colorbar(im, ax=ax_ndvi, shrink=0.8)
    cbar.set_label("NDVI", fontsize=11)

    # Pipeline summary sidebar
    ax_summary.axis("off")
    summary = (
        f"Pipeline Summary\n"
        f"{'─' * 24}\n"
        f"Source:   Earth Search\n"
        f"Scene:   {item.id[:25]}\n"
        f"Date:    {(item.datetime or '')[:10]}\n"
        f"Cloud:   {cc}%\n"
        f"{'─' * 24}\n"
        f"Steps:\n"
        f"  1. STAC search\n"
        f"  2. Range-read B04/B08\n"
        f"  3. NDVI computation\n"
        f"  4. Render output\n"
        f"{'─' * 24}\n"
        f"NDVI Stats:\n"
        f"  Min:  {ndvi.min():>7.3f}\n"
        f"  Max:  {ndvi.max():>7.3f}\n"
        f"  Mean: {ndvi.mean():>7.3f}\n"
        f"  Size: {ndvi.shape[1]}x{ndvi.shape[0]}\n"
    )
    ax_summary.text(
        0.05, 0.95, summary,
        transform=ax_summary.transAxes,
        fontsize=9, fontfamily="monospace",
        verticalalignment="top",
    )

    fig.text(
        0.5, 0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: NDVI map from a real STAC-to-NDVI pipeline workflow. "
        f"Shows vegetation index computed from Sentinel-2 bands B04 and B08 "
        f"over Central Kentucky on {(item.datetime or 'Unknown')[:10]}. "
        f"Brown-white-teal (BrBG) diverging palette. Mean NDVI: {ndvi.mean():.3f}. "
        f"Pipeline summary sidebar shows the 4-step workflow.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {KY_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/pipeline_ndvi_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={KY_BBOX}, "
        f"expression=(B08-B04)/(B08+B04)\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
