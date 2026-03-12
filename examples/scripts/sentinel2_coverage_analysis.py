"""Sentinel-2 temporal coverage analysis for a study area.

Demonstrates a real geospatial analysis workflow: assessing satellite imagery
availability and quality over a study area across multiple seasons. This is
the first step in any remote sensing project — understanding what data exists
before committing to an analysis approach.

Workflow:
  1. Define a study area (Central Kentucky agricultural region)
  2. Search Sentinel-2 L2A across a full growing season (Apr-Oct)
  3. Compute monthly acquisition counts and cloud cover statistics
  4. Identify the best acquisition windows (clearest scenes)
  5. Validate sample COGs for analysis readiness
  6. Output a structured coverage assessment

Data source: Element84 Earth Search (public, no authentication)

Usage::

    python examples/scripts/sentinel2_coverage_analysis.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.raster.info import inspect_raster
from earthforge.raster.validate import validate_cog
from earthforge.stac.search import search_catalog

# ---------------------------------------------------------------------------
# Study area: Central Kentucky agricultural region
# Covers parts of Fayette, Scott, Bourbon, Woodford, and Clark counties.
# This is prime Bluegrass farmland — crop monitoring is a key use case.
# ---------------------------------------------------------------------------
STUDY_AREA = {
    "name": "Central Kentucky Bluegrass",
    "bbox": [-84.8, 37.9, -84.2, 38.3],
    "description": (
        "Inner Bluegrass region of Kentucky — horse farms, tobacco, corn, "
        "and hay production. Flat to gently rolling terrain, EPSG:4326."
    ),
}

# Growing season: April through October
SEASON_START = "2025-04-01"
SEASON_END = "2025-10-31"

# Earth Search — Sentinel-2 L2A (atmospherically corrected)
STAC_API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# Cloud cover threshold for "usable" scenes (< 30%)
CLOUD_THRESHOLD = 30.0


def parse_month(dt_str: str | None) -> str | None:
    """Extract YYYY-MM from an ISO datetime string.

    Parameters:
        dt_str: ISO datetime string or None.

    Returns:
        Month string like '2025-06' or None.
    """
    if not dt_str:
        return None
    try:
        return dt_str[:7]
    except (TypeError, IndexError):
        return None


def format_stats(values: list[float]) -> str:
    """Format a list of floats as min/mean/median/max summary.

    Parameters:
        values: List of numeric values.

    Returns:
        Formatted statistics string.
    """
    if not values:
        return "no data"
    return (
        f"min={min(values):.1f}  mean={statistics.mean(values):.1f}  "
        f"median={statistics.median(values):.1f}  max={max(values):.1f}"
    )


async def search_growing_season(profile: EarthForgeProfile) -> list:
    """Search for all Sentinel-2 acquisitions over the study area.

    Fetches up to 200 items across the full growing season. STAC APIs
    typically return items newest-first, so we get a reverse-chronological
    view of the archive.

    Parameters:
        profile: Configured EarthForge profile with STAC API URL.

    Returns:
        List of SearchResultItem objects.
    """
    print(f"  Bbox:       {STUDY_AREA['bbox']}")
    print(f"  Date range: {SEASON_START} to {SEASON_END}")
    print(f"  Collection: {COLLECTION}")
    print()

    result = await search_catalog(
        profile,
        collections=[COLLECTION],
        bbox=STUDY_AREA["bbox"],
        datetime_range=f"{SEASON_START}/{SEASON_END}",
        max_items=200,
    )

    print(f"  Total matched: {result.matched or 'unknown'}")
    print(f"  Retrieved:     {result.returned} items")
    return result.items


def analyze_temporal_distribution(items: list) -> dict:
    """Analyze the temporal distribution of acquisitions by month.

    Groups items by month and computes per-month counts and cloud cover
    statistics. This tells you which months have the best data availability
    and where gaps exist.

    Parameters:
        items: List of STAC search result items.

    Returns:
        Dict mapping month strings to analysis dicts.
    """
    monthly: dict[str, list] = defaultdict(list)
    for item in items:
        month = parse_month(item.datetime)
        if month:
            monthly[month].append(item)

    analysis = {}
    for month in sorted(monthly.keys()):
        month_items = monthly[month]
        cloud_covers = [
            item.properties.get("eo:cloud_cover", 100.0)
            for item in month_items
            if "eo:cloud_cover" in item.properties
        ]
        usable = [cc for cc in cloud_covers if cc < CLOUD_THRESHOLD]

        analysis[month] = {
            "total_scenes": len(month_items),
            "usable_scenes": len(usable),
            "cloud_covers": cloud_covers,
            "usable_rate": len(usable) / len(month_items) * 100 if month_items else 0,
        }

    return analysis


def identify_best_windows(items: list, top_n: int = 5) -> list:
    """Identify the clearest acquisition dates for the study area.

    Sorts all scenes by cloud cover and returns the top N clearest.
    These are the best candidates for analysis (NDVI, classification, etc.).

    Parameters:
        items: List of STAC search result items.
        top_n: Number of best scenes to return.

    Returns:
        List of (item, cloud_cover) tuples, sorted by cloud cover ascending.
    """
    scored = []
    for item in items:
        cc = item.properties.get("eo:cloud_cover")
        if cc is not None:
            scored.append((item, cc))

    scored.sort(key=lambda x: x[1])
    return scored[:top_n]


async def validate_sample_cogs(items: list, sample_size: int = 3) -> list:
    """Validate COG compliance on a sample of scene assets.

    Picks the clearest scenes and validates their red band (B04) COGs.
    This catches format issues before committing to a large download.

    Parameters:
        items: List of STAC search result items.
        sample_size: Number of scenes to validate.

    Returns:
        List of validation result dicts.
    """
    # Pick the clearest scenes for validation
    scored = identify_best_windows(items, top_n=sample_size)
    results = []

    for item, cloud_cover in scored:
        # Find the red band (B04) — it's the most commonly used for validation
        red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
        if not red_asset:
            continue

        print(f"  Validating {item.id} (cloud: {cloud_cover:.1f}%)...")

        try:
            info = await inspect_raster(red_asset.href)
            validation = await validate_cog(red_asset.href)

            results.append(
                {
                    "item_id": item.id,
                    "cloud_cover": cloud_cover,
                    "dimensions": f"{info.width}x{info.height}",
                    "crs": info.crs,
                    "compression": info.compression,
                    "is_tiled": info.is_tiled,
                    "cog_valid": validation.is_valid,
                    "checks": {c.name: c.passed for c in validation.checks},
                }
            )
        except Exception as exc:
            results.append(
                {
                    "item_id": item.id,
                    "error": str(exc),
                }
            )

    return results


def generate_report(
    items: list,
    monthly: dict,
    best_windows: list,
    validations: list,
) -> dict:
    """Generate a structured coverage assessment report.

    Combines all analysis results into a single JSON-serializable report
    suitable for archiving or downstream processing.

    Parameters:
        items: All retrieved STAC items.
        monthly: Monthly distribution analysis.
        best_windows: Top clearest scenes.
        validations: COG validation results.

    Returns:
        Complete assessment report as a dict.
    """
    all_cloud = [
        item.properties.get("eo:cloud_cover", 100.0)
        for item in items
        if "eo:cloud_cover" in item.properties
    ]

    return {
        "study_area": STUDY_AREA,
        "search_parameters": {
            "collection": COLLECTION,
            "date_range": f"{SEASON_START}/{SEASON_END}",
            "stac_api": STAC_API,
        },
        "summary": {
            "total_scenes": len(items),
            "usable_scenes": sum(1 for cc in all_cloud if cc < CLOUD_THRESHOLD),
            "cloud_cover_stats": {
                "min": round(min(all_cloud), 1) if all_cloud else None,
                "mean": round(statistics.mean(all_cloud), 1) if all_cloud else None,
                "median": round(statistics.median(all_cloud), 1) if all_cloud else None,
                "max": round(max(all_cloud), 1) if all_cloud else None,
            },
            "usable_rate_pct": round(
                sum(1 for cc in all_cloud if cc < CLOUD_THRESHOLD) / len(all_cloud) * 100, 1
            )
            if all_cloud
            else 0,
        },
        "monthly_breakdown": {
            month: {
                "scenes": data["total_scenes"],
                "usable": data["usable_scenes"],
                "usable_rate_pct": round(data["usable_rate"], 1),
            }
            for month, data in monthly.items()
        },
        "best_acquisitions": [
            {
                "id": item.id,
                "datetime": item.datetime,
                "cloud_cover_pct": round(cc, 1),
            }
            for item, cc in best_windows
        ],
        "cog_validation": validations,
        "generated": datetime.now().isoformat(),
    }


async def main() -> None:
    """Run the full Sentinel-2 coverage analysis workflow."""
    print()
    print("=" * 65)
    print("  EarthForge — Sentinel-2 Coverage Analysis")
    print("  Study Area: Central Kentucky Bluegrass")
    print("=" * 65)
    print()

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Step 1: Search the archive
    print("STEP 1: Search Sentinel-2 L2A Archive")
    print("-" * 45)
    items = await search_growing_season(profile)
    print()

    if not items:
        print("No items found. Check network connectivity.")
        return

    # Step 2: Temporal distribution analysis
    print("STEP 2: Monthly Acquisition Analysis")
    print("-" * 45)
    monthly = analyze_temporal_distribution(items)

    all_cloud = [
        item.properties.get("eo:cloud_cover", 100.0)
        for item in items
        if "eo:cloud_cover" in item.properties
    ]

    print(f"  Overall cloud cover: {format_stats(all_cloud)}")
    print(
        f"  Usable scenes (<{CLOUD_THRESHOLD:.0f}% cloud): "
        f"{sum(1 for cc in all_cloud if cc < CLOUD_THRESHOLD)} / {len(items)}"
    )
    print()
    print(f"  {'Month':<10} {'Total':>6} {'Usable':>7} {'Rate':>7}  Cloud Cover Range")
    print(f"  {'-' * 9:<10} {'-' * 5:>6} {'-' * 6:>7} {'-' * 6:>7}  {'-' * 25}")

    for month, data in sorted(monthly.items()):
        cc = data["cloud_covers"]
        cc_range = f"{min(cc):.0f}-{max(cc):.0f}%" if cc else "n/a"
        print(
            f"  {month:<10} {data['total_scenes']:>6} {data['usable_scenes']:>7} "
            f"{data['usable_rate']:>6.1f}%  {cc_range}"
        )
    print()

    # Step 3: Best acquisition windows
    print("STEP 3: Best Acquisition Windows")
    print("-" * 45)
    best = identify_best_windows(items, top_n=8)

    print(f"  Top {len(best)} clearest scenes:")
    for item, cc in best:
        platform = item.properties.get("platform", "?")
        print(f"    {item.datetime[:10]}  {cc:>5.1f}% cloud  {platform}  {item.id}")
    print()

    # Step 4: COG validation on sample
    print("STEP 4: COG Validation (sample)")
    print("-" * 45)
    validations = await validate_sample_cogs(items, sample_size=2)

    for v in validations:
        if "error" in v:
            print(f"    {v['item_id']}: ERROR - {v['error']}")
        else:
            status = "PASS" if v["cog_valid"] else "FAIL"
            print(
                f"    {v['item_id']}: [{status}] {v['dimensions']} {v['crs']} {v['compression']}"
            )
            for check_name, passed in v["checks"].items():
                mark = "OK" if passed else "FAIL"
                print(f"      {check_name}: {mark}")
    print()

    # Step 5: Generate structured report
    print("STEP 5: Assessment Report")
    print("-" * 45)
    report = generate_report(items, monthly, best, validations)

    print(f"  Study area:     {report['study_area']['name']}")
    print(f"  Total scenes:   {report['summary']['total_scenes']}")
    print(f"  Usable scenes:  {report['summary']['usable_scenes']}")
    print(f"  Usable rate:    {report['summary']['usable_rate_pct']}%")
    print(f"  Mean cloud:     {report['summary']['cloud_cover_stats']['mean']}%")
    print()

    # Seasonal recommendation
    best_months = sorted(monthly.items(), key=lambda x: x[1]["usable_rate"], reverse=True)
    if best_months:
        top_month = best_months[0]
        print(
            f"  Recommendation: {top_month[0]} has the highest usable rate "
            f"({top_month[1]['usable_rate']:.0f}%)"
        )
        print("  Schedule field validation or classification analysis for this window.")
    print()

    # Write JSON report
    report_json = json.dumps(report, indent=2, default=str)
    print("  JSON report (first 40 lines):")
    for line in report_json.split("\n")[:40]:
        print(f"    {line}")
    print("    ...")
    print()
    print("Analysis complete.")


if __name__ == "__main__":
    asyncio.run(main())
