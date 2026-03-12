"""Automated geospatial data quality audit across a STAC collection.

Demonstrates a production-style QA pipeline: systematically validating data
quality across an entire STAC collection. This is essential for organizations
that ingest geospatial data at scale — you need automated checks before data
enters your analysis pipeline or data warehouse.

Workflow:
  1. Search a STAC collection for items in a region
  2. For each item, run a battery of quality checks:
     - Metadata completeness (required STAC properties present?)
     - Asset accessibility (can we reach the COG via HTTP?)
     - COG compliance (tiled, compressed, overviews, IFD ordering)
     - CRS consistency (all items in the same projection?)
  3. Aggregate results into a quality scorecard
  4. Flag items that fail checks for review

This pattern scales: swap the STAC API and collection, adjust the checks,
and you have a reusable QA framework for any geospatial archive.

Data source: Element84 Earth Search — Sentinel-2 L2A (public)

Usage::

    python examples/scripts/data_quality_audit.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.raster.info import inspect_raster
from earthforge.raster.validate import validate_cog
from earthforge.stac.info import inspect_stac_item
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# Audit a small area over a short window to keep runtime reasonable
AUDIT_BBOX = [-84.6, 38.0, -84.4, 38.15]  # Lexington, KY
AUDIT_DATE_RANGE = "2025-07/2025-09"
MAX_ITEMS = 10

# Required STAC properties for Sentinel-2 L2A
REQUIRED_PROPERTIES = [
    "datetime",
    "eo:cloud_cover",
    "platform",
    "proj:epsg",
]

# Expected raster properties for Sentinel-2 COGs
EXPECTED_CRS = "EPSG:32616"  # UTM zone 16N for Kentucky


class QualityCheck:
    """Result of a single quality check on a STAC item.

    Attributes:
        name: Check identifier.
        passed: Whether the check passed.
        message: Human-readable detail.
        severity: 'error' for failures, 'warning' for non-blocking issues.
    """

    def __init__(
        self,
        name: str,
        passed: bool,
        message: str,
        severity: str = "error",
    ) -> None:
        self.name = name
        self.passed = passed
        self.message = message
        self.severity = severity

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict.

        Returns:
            Dict with check name, passed status, message, and severity.
        """
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
        }


class ItemAuditResult:
    """Aggregated quality audit result for a single STAC item.

    Attributes:
        item_id: STAC item identifier.
        checks: List of QualityCheck results.
        metadata: Extracted metadata for the report.
    """

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        self.checks: list[QualityCheck] = []
        self.metadata: dict = {}

    @property
    def passed(self) -> bool:
        """Whether all error-severity checks passed."""
        return all(c.passed for c in self.checks if c.severity == "error")

    @property
    def error_count(self) -> int:
        """Number of failed error-severity checks."""
        return sum(1 for c in self.checks if not c.passed and c.severity == "error")

    @property
    def warning_count(self) -> int:
        """Number of failed warning-severity checks."""
        return sum(1 for c in self.checks if not c.passed and c.severity == "warning")

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict.

        Returns:
            Dict with item ID, pass/fail status, checks, and metadata.
        """
        return {
            "item_id": self.item_id,
            "passed": self.passed,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "checks": [c.to_dict() for c in self.checks],
            "metadata": self.metadata,
        }


def check_metadata_completeness(item: object, properties: dict) -> list[QualityCheck]:
    """Check that required STAC properties are present and non-null.

    Parameters:
        item: STAC search result item.
        properties: Item properties dict from STAC info.

    Returns:
        List of QualityCheck results, one per required property.
    """
    checks = []
    for prop in REQUIRED_PROPERTIES:
        present = prop in properties and properties[prop] is not None
        checks.append(QualityCheck(
            name=f"metadata.{prop}",
            passed=present,
            message=f"{prop}: {'present' if present else 'MISSING'}",
        ))
    return checks


def check_crs_consistency(crs: str | None) -> QualityCheck:
    """Check that the raster CRS matches the expected projection.

    For a regional audit (Kentucky), all Sentinel-2 tiles should be in
    the same UTM zone. Mixed CRS in a dataset causes reprojection overhead.

    Parameters:
        crs: CRS string from raster inspection.

    Returns:
        QualityCheck result.
    """
    if crs is None:
        return QualityCheck(
            name="crs_consistency",
            passed=False,
            message="CRS could not be determined",
        )

    # Sentinel-2 tiles over Kentucky could be UTM 16N or 17N
    # depending on exact position. Both are acceptable.
    acceptable_crs = {"EPSG:32616", "EPSG:32617"}
    passed = crs in acceptable_crs
    return QualityCheck(
        name="crs_consistency",
        passed=passed,
        message=f"CRS={crs} ({'expected' if passed else 'unexpected for this region'})",
        severity="warning" if not passed else "error",
    )


async def audit_item(
    profile: EarthForgeProfile,
    item: object,
) -> ItemAuditResult:
    """Run the full quality audit battery on a single STAC item.

    Parameters:
        profile: EarthForge profile for HTTP requests.
        item: STAC search result item.

    Returns:
        ItemAuditResult with all check results.
    """
    result = ItemAuditResult(item.id)
    result.metadata["datetime"] = item.datetime
    result.metadata["cloud_cover"] = item.properties.get("eo:cloud_cover")

    # Check 1: Metadata completeness (from search result properties)
    meta_checks = check_metadata_completeness(item, item.properties)
    result.checks.extend(meta_checks)

    # Check 2: Detailed item inspection (fetch full item JSON)
    if item.self_link:
        try:
            info = await inspect_stac_item(profile, item.self_link)
            result.checks.append(QualityCheck(
                name="item_fetchable",
                passed=True,
                message=f"Item JSON fetched OK ({info.asset_count} assets)",
            ))
            result.metadata["asset_count"] = info.asset_count
            result.metadata["stac_extensions"] = len(info.stac_extensions)
        except Exception as exc:
            result.checks.append(QualityCheck(
                name="item_fetchable",
                passed=False,
                message=f"Failed to fetch item: {exc}",
            ))
            return result
    else:
        result.checks.append(QualityCheck(
            name="item_fetchable",
            passed=False,
            message="No self_link — cannot fetch full item metadata",
            severity="warning",
        ))

    # Check 3: Raster inspection (red band)
    red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
    if red_asset:
        try:
            raster_info = await inspect_raster(red_asset.href)

            result.checks.append(QualityCheck(
                name="raster_accessible",
                passed=True,
                message=f"Red band accessible: {raster_info.width}x{raster_info.height}",
            ))

            result.metadata["dimensions"] = f"{raster_info.width}x{raster_info.height}"
            result.metadata["crs"] = raster_info.crs
            result.metadata["compression"] = raster_info.compression

            # Check CRS consistency
            result.checks.append(check_crs_consistency(raster_info.crs))

            # Check tiling
            result.checks.append(QualityCheck(
                name="raster_tiled",
                passed=raster_info.is_tiled,
                message=f"Tiled: {raster_info.is_tiled} ({raster_info.tile_width}x{raster_info.tile_height})",
            ))

            # Check overviews
            has_overviews = raster_info.overview_count > 0
            result.checks.append(QualityCheck(
                name="raster_overviews",
                passed=has_overviews,
                message=f"Overviews: {raster_info.overview_count} levels",
            ))

            # Check compression
            has_compression = raster_info.compression is not None and raster_info.compression != "none"
            result.checks.append(QualityCheck(
                name="raster_compressed",
                passed=has_compression,
                message=f"Compression: {raster_info.compression or 'none'}",
            ))

        except Exception as exc:
            result.checks.append(QualityCheck(
                name="raster_accessible",
                passed=False,
                message=f"Cannot read raster: {exc}",
            ))
            return result

        # Check 4: Full COG validation (rio-cogeo byte-level checks)
        try:
            cog_result = await validate_cog(red_asset.href)
            result.checks.append(QualityCheck(
                name="cog_valid",
                passed=cog_result.is_valid,
                message=f"COG validation: {'PASS' if cog_result.is_valid else 'FAIL'}",
            ))

            for check in cog_result.checks:
                if not check.passed:
                    result.checks.append(QualityCheck(
                        name=f"cog_{check.name}",
                        passed=False,
                        message=check.message,
                    ))
        except Exception as exc:
            result.checks.append(QualityCheck(
                name="cog_valid",
                passed=False,
                message=f"COG validation error: {exc}",
            ))
    else:
        result.checks.append(QualityCheck(
            name="raster_accessible",
            passed=False,
            message="No red/B04 band asset found in item",
        ))

    return result


def generate_scorecard(results: list[ItemAuditResult]) -> dict:
    """Generate an aggregate quality scorecard across all audited items.

    Parameters:
        results: List of per-item audit results.

    Returns:
        Scorecard dict with pass rates, common failures, and recommendations.
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for c in r.checks if c.passed) for r in results)

    # Count failure types
    failure_counter: Counter = Counter()
    for r in results:
        for c in r.checks:
            if not c.passed:
                failure_counter[c.name] += 1

    # CRS distribution
    crs_counter: Counter = Counter()
    for r in results:
        crs = r.metadata.get("crs")
        if crs:
            crs_counter[crs] += 1

    scorecard = {
        "items_audited": total,
        "items_passed": passed,
        "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        "total_checks_run": total_checks,
        "checks_passed": passed_checks,
        "check_pass_rate_pct": round(passed_checks / total_checks * 100, 1) if total_checks else 0,
        "top_failures": dict(failure_counter.most_common(5)),
        "crs_distribution": dict(crs_counter),
        "recommendations": [],
    }

    # Generate recommendations
    if scorecard["pass_rate_pct"] == 100:
        scorecard["recommendations"].append(
            "All items pass quality checks. Data is ready for analysis."
        )
    else:
        if "cog_valid" in failure_counter:
            scorecard["recommendations"].append(
                f"{failure_counter['cog_valid']} items fail COG validation — "
                "consider re-processing with gdal_translate -of COG."
            )
        if "raster_overviews" in failure_counter:
            scorecard["recommendations"].append(
                f"{failure_counter['raster_overviews']} items missing overviews — "
                "run gdaladdo to add pyramids."
            )
        if len(crs_counter) > 1:
            scorecard["recommendations"].append(
                f"Mixed CRS detected ({dict(crs_counter)}). Reproject to a "
                "common CRS before mosaicking."
            )

    return scorecard


async def main() -> None:
    """Run the full data quality audit pipeline."""
    print()
    print("#" * 60)
    print("  EarthForge — Data Quality Audit Pipeline")
    print(f"  Collection: {COLLECTION}")
    print("#" * 60)
    print()
    print(f"  STAC API:    {STAC_API}")
    print(f"  Collection:  {COLLECTION}")
    print(f"  BBox:        {AUDIT_BBOX}")
    print(f"  Date range:  {AUDIT_DATE_RANGE}")
    print(f"  Max items:   {MAX_ITEMS}")

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Step 1: Search for items to audit
    print()
    print("STEP 1: Discover Items")
    print("-" * 45)
    result = await search_catalog(
        profile,
        collections=[COLLECTION],
        bbox=AUDIT_BBOX,
        datetime_range=AUDIT_DATE_RANGE,
        max_items=MAX_ITEMS,
    )

    items = result.items
    print(f"  Found {len(items)} items to audit")
    print()

    if not items:
        print("  No items found. Check parameters.")
        return

    # Step 2: Audit each item
    print("STEP 2: Run Quality Checks")
    print("-" * 45)
    audit_results: list[ItemAuditResult] = []

    for i, item in enumerate(items, 1):
        cc = item.properties.get("eo:cloud_cover", "?")
        print(f"  [{i}/{len(items)}] {item.id} (cloud: {cc}%)")

        result = await audit_item(profile, item)
        audit_results.append(result)

        status = "PASS" if result.passed else "FAIL"
        errors = f" ({result.error_count} errors)" if result.error_count else ""
        warnings = f" ({result.warning_count} warnings)" if result.warning_count else ""
        print(f"         -> {status}{errors}{warnings}")

        # Print failed checks
        for check in result.checks:
            if not check.passed:
                icon = "!!" if check.severity == "error" else "??"
                print(f"            [{icon}] {check.name}: {check.message}")
    print()

    # Step 3: Generate scorecard
    print("STEP 3: Quality Scorecard")
    print("-" * 45)
    scorecard = generate_scorecard(audit_results)

    print(f"  Items audited:    {scorecard['items_audited']}")
    print(f"  Items passed:     {scorecard['items_passed']}")
    print(f"  Pass rate:        {scorecard['pass_rate_pct']}%")
    print(f"  Checks run:       {scorecard['total_checks_run']}")
    print(f"  Checks passed:    {scorecard['checks_passed']}")
    print(f"  Check pass rate:  {scorecard['check_pass_rate_pct']}%")

    if scorecard["crs_distribution"]:
        print(f"  CRS distribution: {scorecard['crs_distribution']}")

    if scorecard["top_failures"]:
        print()
        print("  Top failure types:")
        for name, count in scorecard["top_failures"].items():
            print(f"    {name}: {count} items")

    if scorecard["recommendations"]:
        print()
        print("  Recommendations:")
        for rec in scorecard["recommendations"]:
            print(f"    - {rec}")
    print()

    # Step 4: Detailed report
    print("STEP 4: Detailed Report")
    print("-" * 45)

    report = {
        "audit_parameters": {
            "stac_api": STAC_API,
            "collection": COLLECTION,
            "bbox": AUDIT_BBOX,
            "date_range": AUDIT_DATE_RANGE,
        },
        "scorecard": scorecard,
        "items": [r.to_dict() for r in audit_results],
        "generated": datetime.now().isoformat(),
    }

    # Show items that failed
    failed = [r for r in audit_results if not r.passed]
    if failed:
        print(f"  {len(failed)} item(s) require attention:")
        for r in failed:
            print(f"    {r.item_id}: {r.error_count} errors, {r.warning_count} warnings")
    else:
        print("  All items passed quality checks.")
    print()

    report_json = json.dumps(report, indent=2, default=str)
    print(f"  Report size: {len(report_json):,} bytes")
    print("  (Write to file with: json.dump(report, open('audit.json', 'w')))")
    print()
    print("Audit complete.")


if __name__ == "__main__":
    asyncio.run(main())
