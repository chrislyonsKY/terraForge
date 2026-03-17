"""Sentinel-2 NDVI -- Netherlands, Rotterdam / Delft urban-water contrast.

Computes NDVI from Sentinel-2 over the Rotterdam/Delft area in the
Netherlands, demonstrating the NDVI contrast between urban areas (low),
waterways (very low/negative), and parks/agricultural fields (moderate
to high).

Output: examples/outputs/ndvi_netherlands_rotterdam.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/sentinel2_netherlands_demo.py
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
# Rotterdam / Delft area, Netherlands
NL_BBOX = [4.2, 51.8, 4.6, 52.1]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "ndvi_netherlands_rotterdam.png"
OUTPUT_TXT = OUTPUT_DIR / "ndvi_netherlands_rotterdam.txt"


async def main() -> None:
    """Generate NDVI map of Rotterdam/Delft showing urban-water contrast."""
    print("EarthForge -- NDVI Demo: Netherlands (Rotterdam/Delft)")
    print("=" * 57)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for clear Sentinel-2 scenes over the Netherlands...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=NL_BBOX,
        datetime_range="2025-05-01/2025-09-30",
        max_items=25,
    )

    candidates = [
        item for item in result.items if (item.properties.get("eo:cloud_cover") or 100) < 20
    ]
    if not candidates:
        print("No clear scenes found. Cloud cover is frequent in NL.")
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
            native_bounds = transform_bounds("EPSG:4326", src.crs, *NL_BBOX)
        else:
            native_bounds = NL_BBOX
        window = from_bounds(*native_bounds, transform=src.transform)
        red = src.read(1, window=window).astype(np.float32)

    print("Reading NIR band...")
    with rasterio.open(nir_asset.href) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            native_bounds = transform_bounds("EPSG:4326", src.crs, *NL_BBOX)
        else:
            native_bounds = NL_BBOX
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

    # Land cover class percentages
    water_pct = np.sum(ndvi < 0.0) / ndvi.size * 100
    urban_pct = np.sum((ndvi >= 0.0) & (ndvi < 0.2)) / ndvi.size * 100
    veg_pct = np.sum(ndvi >= 0.3) / ndvi.size * 100
    print(f"  Water (NDVI<0): {water_pct:.1f}%")
    print(f"  Urban (0-0.2):  {urban_pct:.1f}%")
    print(f"  Vegetation (>0.3): {veg_pct:.1f}%")

    # Render
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    brbg_colors = [tuple(int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)) for h in DIVERGING_BRBG]
    cmap = LinearSegmentedColormap.from_list("brbg", brbg_colors, N=256)

    fig, (ax_map, ax_bar) = plt.subplots(
        1,
        2,
        figsize=(13, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    im = ax_map.imshow(ndvi, cmap=cmap, vmin=-0.3, vmax=0.9, aspect="auto")

    ax_map.set_title(
        f"NDVI -- Rotterdam / Delft, Netherlands\n"
        f"Sentinel-2 | {(item.datetime or 'Unknown')[:10]} | {crs_str}",
        fontsize=13,
        fontweight="bold",
    )
    ax_map.set_xlabel("Pixels (east-west)", fontsize=10)
    ax_map.set_ylabel("Pixels (north-south)", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)

    # Land cover class bar chart
    classes = ["Water\n(<0)", "Urban\n(0-0.2)", "Trans.\n(0.2-0.3)", "Veg.\n(>0.3)"]
    trans_pct = np.sum((ndvi >= 0.2) & (ndvi < 0.3)) / ndvi.size * 100
    values = [water_pct, urban_pct, trans_pct, veg_pct]
    bar_colors = ["#8c510a", "#dfc27d", "#c7eae5", "#01665e"]

    bars = ax_bar.barh(classes, values, color=bar_colors, edgecolor="gray", linewidth=0.5)
    ax_bar.set_xlabel("% of Pixels", fontsize=10)
    ax_bar.set_title("NDVI Classes", fontsize=11)
    ax_bar.grid(True, alpha=0.3, axis="x")

    for bar, val in zip(bars, values, strict=False):
        ax_bar.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va="center",
            fontsize=9,
        )

    fig.text(
        0.5,
        0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
        f"Palette: BrBG (colorblind-safe) | Rotterdam/Delft, NL | "
        f"EarthForge v1.0.0 | {datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center",
        fontsize=7,
        color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: NDVI map of the Rotterdam/Delft area in the Netherlands from "
        f"Sentinel-2 data dated {(item.datetime or 'Unknown')[:10]}. The map shows "
        f"the contrast between water bodies (brown, NDVI < 0, {water_pct:.1f}%), "
        f"urban areas (tan, NDVI 0-0.2, {urban_pct:.1f}%), and vegetation/parks "
        f"(teal, NDVI > 0.3, {veg_pct:.1f}%). A sidebar bar chart breaks down "
        f"NDVI class percentages. BrBG diverging palette.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {red_asset.href}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {NL_BBOX}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/sentinel2_netherlands_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={NL_BBOX}\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
