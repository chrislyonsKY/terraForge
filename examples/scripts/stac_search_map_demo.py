"""STAC search results map — Sentinel-2 footprints over Kentucky.

Generates a map showing STAC item footprints from a Sentinel-2 search,
color-coded by cloud cover. Demonstrates the earthforge STAC search
module with real data from Element84 Earth Search.

Output: examples/outputs/stac_search_results_map.png

Data source: Sentinel-2 L2A via Element84 Earth Search (public)

Usage::

    python examples/scripts/stac_search_map_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
KY_BBOX = [-85.5, 37.0, -84.0, 38.5]
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "stac_search_results_map.png"
OUTPUT_TXT = OUTPUT_DIR / "stac_search_results_map.txt"


async def main() -> None:
    """Generate STAC search results map."""
    print("EarthForge — STAC Search Demo: Sentinel-2 Footprints")
    print("=" * 57)

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    print("Searching for Sentinel-2 scenes over Kentucky...")
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=KY_BBOX,
        datetime_range="2025-06-01/2025-08-31",
        max_items=30,
    )

    print(f"Found {len(result.items)} items")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import Normalize
        from matplotlib.patches import Rectangle
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    # Draw the search bbox
    bbox_w = KY_BBOX[2] - KY_BBOX[0]
    bbox_h = KY_BBOX[3] - KY_BBOX[1]
    ax.add_patch(
        Rectangle(
            (KY_BBOX[0], KY_BBOX[1]),
            bbox_w,
            bbox_h,
            linewidth=2,
            edgecolor="black",
            facecolor="lightgray",
            alpha=0.3,
            linestyle="--",
            label="Search bbox",
        )
    )

    # Plot item footprints colored by cloud cover
    cmap = plt.cm.viridis_r  # reversed so low cloud = bright
    norm = Normalize(vmin=0, vmax=100)

    for item in result.items:
        cc = item.properties.get("eo:cloud_cover", 50)
        color = cmap(norm(cc))

        # Use item bbox as rectangle
        if hasattr(item, "bbox") and item.bbox:
            parts = (
                item.bbox
                if isinstance(item.bbox, list)
                else [
                    item.bbox.get("west", 0),
                    item.bbox.get("south", 0),
                    item.bbox.get("east", 0),
                    item.bbox.get("north", 0),
                ]
            )
            if len(parts) >= 4:
                w = parts[2] - parts[0]
                h = parts[3] - parts[1]
                ax.add_patch(
                    Rectangle(
                        (parts[0], parts[1]),
                        w,
                        h,
                        linewidth=0.8,
                        edgecolor=color,
                        facecolor=color,
                        alpha=0.4,
                    )
                )

    ax.set_xlim(KY_BBOX[0] - 0.5, KY_BBOX[2] + 0.5)
    ax.set_ylim(KY_BBOX[1] - 0.3, KY_BBOX[3] + 0.3)
    ax.set_aspect("equal")

    ax.set_title(
        f"STAC Search Results — Sentinel-2 L2A\n"
        f"Kentucky | Jun-Aug 2025 | {len(result.items)} scenes",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)

    # Colorbar
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Cloud Cover (%)", fontsize=11)

    fig.text(
        0.5,
        0.01,
        f"Data: Copernicus Sentinel-2 via Earth Search | "
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
        f"Alt Text: Map showing {len(result.items)} Sentinel-2 scene footprints "
        f"over Central Kentucky from June-August 2025. Footprints are color-coded "
        f"by cloud cover percentage using a reversed viridis palette (bright = low "
        f"cloud, dark = high cloud). A dashed rectangle shows the search bounding box.\n\n"
        f"Data Source: Copernicus, Sentinel-2 Level-2A\n"
        f"URL: {STAC_API}\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Sentinel Data Terms\n"
        f"Spatial Extent: {KY_BBOX}\n"
        f"Temporal Extent: 2025-06-01 / 2025-08-31\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/stac_search_map_demo.py\n"
        f"Parameters: collection=sentinel-2-l2a, bbox={KY_BBOX}, "
        f"datetime=2025-06-01/2025-08-31, max_items=30\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    asyncio.run(main())
