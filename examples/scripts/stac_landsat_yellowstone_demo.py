"""STAC Landsat search — Yellowstone National Park scene footprints.

Searches Element84 Earth Search for Landsat Collection 2 Level-2 scenes
over Yellowstone National Park, then renders scene footprints colored by
cloud cover percentage.

Output: examples/outputs/stac_landsat_yellowstone.png

Data source: Landsat Collection 2 Level-2 via Element84 Earth Search (public)

Usage::

    python examples/scripts/stac_landsat_yellowstone_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.core.palettes import VIRIDIS
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
# Yellowstone National Park
YS_BBOX = [-111.2, 44.1, -110.0, 45.0]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "stac_landsat_yellowstone.png"
OUTPUT_TXT = OUTPUT_DIR / "stac_landsat_yellowstone.txt"


async def main() -> None:
    """Search Landsat scenes over Yellowstone and render footprints."""
    print("EarthForge -- STAC Demo: Landsat Yellowstone NP")
    print("=" * 52)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for Landsat C2-L2 scenes over Yellowstone...")
    result = await search_catalog(
        profile,
        collections=["landsat-c2-l2"],
        bbox=YS_BBOX,
        datetime_range="2025-06-01/2025-09-30",
        max_items=40,
    )

    print(f"Found {len(result.items)} items")
    if not result.items:
        print("No items found. Check network connectivity.")
        return

    # Render
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(11, 8))

    # Draw search bbox
    bbox_w = YS_BBOX[2] - YS_BBOX[0]
    bbox_h = YS_BBOX[3] - YS_BBOX[1]
    ax.add_patch(Rectangle(
        (YS_BBOX[0], YS_BBOX[1]), bbox_w, bbox_h,
        linewidth=2, edgecolor="black", facecolor="lightgray",
        alpha=0.3, linestyle="--", label="Search bbox",
    ))

    # Color footprints by cloud cover
    cmap = plt.cm.viridis_r
    norm = Normalize(vmin=0, vmax=100)

    cloud_values = []
    for item in result.items:
        cc = item.properties.get("eo:cloud_cover", 50)
        cloud_values.append(cc)
        color = cmap(norm(cc))

        if item.bbox and len(item.bbox) >= 4:
            w = item.bbox[2] - item.bbox[0]
            h = item.bbox[3] - item.bbox[1]
            ax.add_patch(Rectangle(
                (item.bbox[0], item.bbox[1]), w, h,
                linewidth=0.8, edgecolor=color,
                facecolor=color, alpha=0.35,
            ))

    ax.set_xlim(YS_BBOX[0] - 0.5, YS_BBOX[2] + 0.5)
    ax.set_ylim(YS_BBOX[1] - 0.3, YS_BBOX[3] + 0.3)
    ax.set_aspect("equal")

    ax.set_title(
        f"STAC Search Results -- Landsat C2-L2\n"
        f"Yellowstone NP | Jun-Sep 2025 | {len(result.items)} scenes",
        fontsize=13, fontweight="bold",
    )
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)

    # Colorbar
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Cloud Cover (%)", fontsize=11)

    # Stats annotation
    mean_cc = np.mean(cloud_values) if cloud_values else 0
    ax.text(
        0.02, 0.02,
        f"Mean cloud: {mean_cc:.1f}%  |  Scenes: {len(result.items)}",
        transform=ax.transAxes, fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
    )

    fig.text(
        0.5, 0.01,
        f"Data: USGS Landsat C2-L2 via Earth Search | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    # Sidecar
    sidecar = (
        f"Alt Text: Map showing {len(result.items)} Landsat Collection 2 Level-2 "
        f"scene footprints over Yellowstone National Park from June-September 2025. "
        f"Footprints are color-coded by cloud cover percentage using a reversed "
        f"viridis palette (bright = clear, dark = cloudy). Mean cloud cover is "
        f"{mean_cc:.1f}%. A dashed rectangle marks the search bounding box.\n\n"
        f"Data Source: USGS, Landsat Collection 2 Level-2\n"
        f"URL: {STAC_API}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: USGS Landsat Data Policy (public domain)\n"
        f"Spatial Extent: {YS_BBOX}\n"
        f"Temporal Extent: 2025-06-01 / 2025-09-30\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/stac_landsat_yellowstone_demo.py\n"
        f"Parameters: collection=landsat-c2-l2, bbox={YS_BBOX}, "
        f"datetime=2025-06-01/2025-09-30, max_items=40\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
