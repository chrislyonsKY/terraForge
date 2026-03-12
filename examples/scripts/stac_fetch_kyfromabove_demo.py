"""Real-world demo: fetch COG assets from KyFromAbove STAC API.

Searches the KyFromAbove STAC API for aerial orthoimagery over Lexington, KY
(orthos-phase3 collection), then downloads the thumbnail and COG data asset
using earthforge.stac.fetch. Demonstrates parallel download and resume support.

Run:
    python examples/stac_fetch_kyfromabove_demo.py

Requirements: pip install earthforge[stac]
"""

import asyncio
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.fetch import fetch_assets
from earthforge.stac.search import search_catalog

# ---------------------------------------------------------------------------
# KyFromAbove STAC API — aerial imagery, LiDAR, and DEMs for Kentucky.
# orthos-phase3 provides 3-inch leaf-off COGs captured 2024.
# ---------------------------------------------------------------------------
KYFROMABOVE_STAC = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com/"
COLLECTION = "orthos-phase3"

# Lexington, KY bounding box
LEXINGTON_BBOX = [-84.57, 37.97, -84.43, 38.08]

OUTPUT_DIR = Path("data/kyfromabove_fetch")


async def main() -> None:
    profile = EarthForgeProfile(
        name="kyfromabove",
        stac_api=KYFROMABOVE_STAC,
        storage_backend="local",
    )

    print("=" * 60)
    print("EarthForge stac fetch — KyFromAbove Orthoimagery Demo")
    print("=" * 60)

    # Step 1: Search for orthoimagery over Lexington
    print(f"\nSearching {COLLECTION!r} over Lexington bbox: {LEXINGTON_BBOX}")
    results = await search_catalog(
        profile,
        collections=[COLLECTION],
        bbox=LEXINGTON_BBOX,
        max_items=3,
    )
    print(f"  Found {len(results.items)} item(s)")

    if not results.items:
        print("  No items found — check the bbox or try a different collection.")
        return

    # Step 2: Inspect the first item
    first_item = results.items[0]
    print(f"\n  Item: {first_item.id}")
    print(f"  Datetime: {first_item.datetime}")
    print(f"  Collection: {first_item.collection}")
    print(f"  Assets ({first_item.asset_count}):")
    for asset in first_item.assets:
        print(f"    {asset.key:<12} {asset.media_type or 'unknown'}")
        print(f"               {asset.href[:80]}...")

    # Step 3: Pick what to fetch
    # Thumbnail is small (~50-200 KB) - good for demo without pulling a full COG
    # Data asset is the full 3-inch COG (can be hundreds of MB)
    thumbnail_key = next(
        (
            a.key
            for a in first_item.assets
            if a.key == "thumbnail" or "png" in (a.media_type or "")
        ),
        None,
    )
    data_key = next(
        (a.key for a in first_item.assets if "tiff" in (a.media_type or "").lower()),
        None,
    )

    # For demo: fetch thumbnail + metadata (small files), skip full COG
    fetch_keys: list[str] = []
    if thumbnail_key:
        fetch_keys.append(thumbnail_key)
    if data_key:
        # Uncomment to fetch the full COG (~hundreds of MB):
        # fetch_keys.append(data_key)
        print(f"\n  Note: data asset ({data_key!r}) is a full 3-inch COG and may be")
        print("  hundreds of MB. Fetching thumbnail only for this demo.")
        print(f"  To fetch the COG: add {data_key!r} to fetch_keys in the script.")

    if not fetch_keys:
        fetch_keys = [first_item.assets[0].key]

    item_url = (
        f"{KYFROMABOVE_STAC.rstrip('/')}/collections/{first_item.collection}/items/{first_item.id}"
    )

    print(f"\nFetching {fetch_keys} from {first_item.id}...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = await fetch_assets(
        profile,
        item_url=item_url,
        output_dir=str(OUTPUT_DIR / first_item.id),
        assets=fetch_keys,
        parallel=2,
    )

    # Step 4: Report results
    print(f"\nFetch complete in {result.elapsed_seconds:.2f}s")
    print(f"  Output dir:        {result.output_dir}")
    print(f"  Assets requested:  {result.assets_requested}")
    print(f"  Downloaded:        {result.assets_fetched}")
    print(f"  Skipped (resumed): {result.assets_skipped}")
    print(f"  Bytes downloaded:  {result.total_bytes_downloaded:,}")
    print(f"  Total on disk:     {result.total_size_bytes:,}")
    print()
    print("  Files:")
    for f in result.files:
        status = "SKIP" if f.skipped else "DONE"
        print(f"    [{status}] {Path(f.local_path).name} ({f.size_bytes:,} bytes)")

    # Step 5: Demonstrate resume — run again, files should be skipped
    if result.assets_fetched > 0:
        print("\nRunning fetch again to demonstrate resume...")
        result2 = await fetch_assets(
            profile,
            item_url=item_url,
            output_dir=str(OUTPUT_DIR / first_item.id),
            assets=fetch_keys,
            parallel=2,
        )
        if result2.assets_skipped == result2.assets_requested:
            print(f"  All {result2.assets_skipped} asset(s) skipped — resume working correctly.")
        else:
            print(f"  Downloaded: {result2.assets_fetched}, Skipped: {result2.assets_skipped}")


if __name__ == "__main__":
    asyncio.run(main())
