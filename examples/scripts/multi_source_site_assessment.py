"""Multi-source geospatial data assessment for a project site.

A common GIS workflow: before starting any spatial analysis project, you need
to inventory what data is available across multiple sources, check its quality,
and identify gaps. This example combines STAC search, raster inspection, COG
validation, and vector spatial queries into a single site assessment.

Scenario: A conservation organization is evaluating land in Eastern Kentucky
for a potential reforestation project. They need to know what satellite imagery,
elevation data, and protected area boundaries are available for the study area.

Workflow:
  1. Define the project site (Daniel Boone National Forest region)
  2. Search multiple STAC collections (Sentinel-2 imagery, Copernicus DEM)
  3. Inspect raster properties on sample assets (resolution, CRS, tiling)
  4. Fetch and query vector boundaries (Wildlife Management Areas)
  5. Cross-reference: which WMAs fall within the project bbox?
  6. Generate a data inventory report

Data sources:
  - Element84 Earth Search (Sentinel-2, Copernicus DEM) — public
  - KY Wildlife Management Areas (ArcGIS MapServer) — public

Usage::

    python examples/scripts/multi_source_site_assessment.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")
sys.path.insert(0, "packages/vector/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.raster.info import inspect_raster
from earthforge.raster.validate import validate_cog
from earthforge.stac.search import search_catalog
from earthforge.vector.convert import convert_vector
from earthforge.vector.query import query_features

# ---------------------------------------------------------------------------
# Project site: Eastern Kentucky — Daniel Boone National Forest region
# Rugged Appalachian terrain with mixed hardwood forest, strip-mined lands,
# and small agricultural valleys. Prime candidate for reforestation assessment.
# ---------------------------------------------------------------------------
PROJECT_SITE = {
    "name": "Daniel Boone NF — Red River Gorge Region",
    "bbox": [-83.9, 37.7, -83.4, 37.95],
    "description": (
        "Eastern Kentucky Appalachian region encompassing parts of the "
        "Daniel Boone National Forest, Red River Gorge Geological Area, "
        "and surrounding strip-mine reclamation lands."
    ),
    "crs": "EPSG:4326",
    "area_km2": "~1,200",
}

EARTH_SEARCH_API = "https://earth-search.aws.element84.com/v1"

# ArcGIS REST endpoint for KY Wildlife Management Areas
WMA_SERVICE_URL = (
    "https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services"
    "/Ky_Public_Hunting_Areas_WGS84WM/MapServer/1"
)


def _esri_polygon_to_geojson(geom: dict) -> dict:
    """Convert Esri JSON polygon geometry to GeoJSON.

    Parameters:
        geom: Esri JSON geometry with ``rings``.

    Returns:
        GeoJSON geometry dict.
    """
    rings = geom.get("rings", [])
    if not rings:
        return {"type": "Polygon", "coordinates": []}
    return {"type": "Polygon", "coordinates": rings}


async def assess_sentinel2(profile: EarthForgeProfile) -> dict:
    """Assess Sentinel-2 imagery availability for the project site.

    Searches for recent cloud-free imagery and inspects a sample COG
    to verify format compliance and resolution.

    Parameters:
        profile: EarthForge profile with STAC API configured.

    Returns:
        Assessment dict with search results and sample inspection.
    """
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=PROJECT_SITE["bbox"],
        datetime_range="2025-06/2025-09",
        max_items=20,
    )

    cloud_covers = [
        item.properties.get("eo:cloud_cover", 100.0)
        for item in result.items
        if "eo:cloud_cover" in item.properties
    ]
    usable = [cc for cc in cloud_covers if cc < 30]

    assessment = {
        "collection": "sentinel-2-l2a",
        "total_scenes": result.returned,
        "matched": result.matched,
        "usable_scenes_lt30pct_cloud": len(usable),
        "date_range": "2025-06 to 2025-09",
        "sample_inspection": None,
        "cog_validation": None,
    }

    # Inspect a sample COG (red band from clearest scene)
    if result.items:
        scored = sorted(
            result.items,
            key=lambda i: i.properties.get("eo:cloud_cover", 100),
        )
        best = scored[0]
        red = next((a for a in best.assets if a.key in ("red", "B04")), None)
        if red:
            try:
                info = await inspect_raster(red.href)
                assessment["sample_inspection"] = {
                    "item_id": best.id,
                    "cloud_cover": best.properties.get("eo:cloud_cover"),
                    "dimensions": f"{info.width}x{info.height}",
                    "crs": info.crs,
                    "bands": info.band_count,
                    "compression": info.compression,
                    "tiled": info.is_tiled,
                    "overviews": info.overview_count,
                }

                val = await validate_cog(red.href)
                assessment["cog_validation"] = {
                    "is_valid": val.is_valid,
                    "checks": {c.name: c.passed for c in val.checks},
                }
            except Exception as exc:
                assessment["sample_inspection"] = {"error": str(exc)}

    return assessment


async def assess_dem(profile: EarthForgeProfile) -> dict:
    """Assess DEM data availability for the project site.

    Searches the Copernicus DEM 30m collection to determine elevation
    data coverage.

    Parameters:
        profile: EarthForge profile with STAC API configured.

    Returns:
        Assessment dict with DEM tile information.
    """
    result = await search_catalog(
        profile,
        collections=["cop-dem-glo-30"],
        bbox=PROJECT_SITE["bbox"],
        max_items=20,
    )

    assessment = {
        "collection": "cop-dem-glo-30",
        "resolution": "30m",
        "tiles_found": result.returned,
        "tile_ids": [item.id for item in result.items],
        "sample_inspection": None,
    }

    # Inspect a sample DEM tile
    if result.items:
        first = result.items[0]
        data_asset = next(
            (a for a in first.assets if a.key in ("data", "dem")),
            first.assets[0] if first.assets else None,
        )
        if data_asset:
            try:
                info = await inspect_raster(data_asset.href)
                assessment["sample_inspection"] = {
                    "tile_id": first.id,
                    "dimensions": f"{info.width}x{info.height}",
                    "crs": info.crs,
                    "dtype": info.bands[0].dtype if info.bands else "unknown",
                    "compression": info.compression,
                    "tiled": info.is_tiled,
                }
            except Exception as exc:
                assessment["sample_inspection"] = {"error": str(exc)}

    return assessment


def fetch_wma_geojson_for_bbox(bbox: list[float]) -> dict:
    """Fetch Wildlife Management Areas intersecting a bounding box.

    Queries the KY ArcGIS REST API with a spatial filter to find WMAs
    within the project site.

    Parameters:
        bbox: Bounding box [west, south, east, north] in EPSG:4326.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    data = {
        "where": "1=1",
        "geometry": json.dumps({
            "xmin": bbox[0],
            "ymin": bbox[1],
            "xmax": bbox[2],
            "ymax": bbox[3],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "AREANAME,WMA,ACRES_CAL,Counties,MANAGER",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }

    r = httpx.post(f"{WMA_SERVICE_URL}/query", data=data, timeout=120)
    r.raise_for_status()
    esri_json = r.json()

    features = []
    for feat in esri_json.get("features", []):
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        features.append({
            "type": "Feature",
            "properties": attrs,
            "geometry": _esri_polygon_to_geojson(geom),
        })

    return {"type": "FeatureCollection", "features": features}


async def assess_vector_boundaries() -> dict:
    """Assess protected area boundaries within the project site.

    Fetches KY Wildlife Management Areas from the ArcGIS REST API,
    converts to GeoParquet, and runs a spatial query to identify WMAs
    overlapping the project bbox.

    Returns:
        Assessment dict with boundary information.
    """
    assessment = {
        "source": "KY Public Hunting Areas (ArcGIS MapServer)",
        "wmas_in_bbox": 0,
        "wma_details": [],
        "total_protected_acres": 0,
        "geoparquet_valid": False,
    }

    try:
        geojson = fetch_wma_geojson_for_bbox(PROJECT_SITE["bbox"])
        feature_count = len(geojson["features"])
        assessment["wmas_in_bbox"] = feature_count

        if feature_count == 0:
            return assessment

        # Convert to GeoParquet and verify roundtrip
        with tempfile.TemporaryDirectory() as tmp:
            geojson_path = Path(tmp) / "wma.geojson"
            geojson_path.write_text(json.dumps(geojson))

            parquet_path = str(Path(tmp) / "wma.parquet")
            convert_result = await convert_vector(str(geojson_path), output=parquet_path)
            assessment["geoparquet_valid"] = convert_result.feature_count == feature_count

            # Query to verify spatial filtering works
            query_result = await query_features(
                parquet_path,
                bbox=PROJECT_SITE["bbox"],
                columns=["AREANAME", "ACRES_CAL", "Counties", "MANAGER"],
                include_geometry=False,
            )

            total_acres = 0
            for f in query_result.features:
                name = f.get("AREANAME", "Unknown")
                acres = f.get("ACRES_CAL", 0) or 0
                total_acres += acres
                assessment["wma_details"].append({
                    "name": name,
                    "acres": round(acres),
                    "counties": f.get("Counties", ""),
                    "manager": f.get("MANAGER", ""),
                })

            assessment["total_protected_acres"] = round(total_acres)

    except Exception as exc:
        assessment["error"] = str(exc)

    return assessment


def print_section(title: str) -> None:
    """Print a formatted section header.

    Parameters:
        title: Section title text.
    """
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def main() -> None:
    """Run the full multi-source site assessment."""
    print()
    print("#" * 60)
    print("  EarthForge — Multi-Source Site Assessment")
    print(f"  {PROJECT_SITE['name']}")
    print("#" * 60)
    print()
    print(f"  Site:        {PROJECT_SITE['name']}")
    print(f"  BBox:        {PROJECT_SITE['bbox']}")
    print(f"  Area:        {PROJECT_SITE['area_km2']}")
    print(f"  Description: {PROJECT_SITE['description']}")

    profile = EarthForgeProfile(name="earth-search", stac_api=EARTH_SEARCH_API)
    report = {
        "project_site": PROJECT_SITE,
        "generated": datetime.now().isoformat(),
        "data_sources": {},
    }

    # Source 1: Sentinel-2 Imagery
    print_section("Source 1: Sentinel-2 L2A Imagery")
    print("  Searching Element84 Earth Search...")
    s2 = await assess_sentinel2(profile)
    report["data_sources"]["sentinel2"] = s2

    print(f"  Scenes found:    {s2['total_scenes']} (matched: {s2['matched']})")
    print(f"  Usable (<30%cc): {s2['usable_scenes_lt30pct_cloud']}")
    if s2["sample_inspection"] and "error" not in s2["sample_inspection"]:
        si = s2["sample_inspection"]
        print(f"  Sample COG:      {si['item_id']}")
        print(f"    Dimensions:    {si['dimensions']}")
        print(f"    CRS:           {si['crs']}")
        print(f"    Compression:   {si['compression']}")
        if s2["cog_validation"]:
            valid = "PASS" if s2["cog_validation"]["is_valid"] else "FAIL"
            print(f"    COG valid:     {valid}")

    # Source 2: Copernicus DEM
    print_section("Source 2: Copernicus DEM 30m")
    print("  Searching Element84 Earth Search...")
    dem = await assess_dem(profile)
    report["data_sources"]["copernicus_dem"] = dem

    print(f"  DEM tiles found: {dem['tiles_found']}")
    print(f"  Resolution:      {dem['resolution']}")
    if dem["tile_ids"]:
        for tid in dem["tile_ids"][:5]:
            print(f"    - {tid}")
    if dem["sample_inspection"] and "error" not in dem["sample_inspection"]:
        di = dem["sample_inspection"]
        print(f"  Sample tile:     {di['tile_id']}")
        print(f"    Dimensions:    {di['dimensions']}")
        print(f"    CRS:           {di['crs']}")
        print(f"    Dtype:         {di['dtype']}")

    # Source 3: Vector boundaries (WMAs)
    print_section("Source 3: KY Wildlife Management Areas")
    print("  Querying ArcGIS MapServer...")
    wma = await assess_vector_boundaries()
    report["data_sources"]["wildlife_management_areas"] = wma

    print(f"  WMAs in bbox:    {wma['wmas_in_bbox']}")
    print(f"  Total acres:     {wma['total_protected_acres']:,}")
    print(f"  GeoParquet OK:   {wma['geoparquet_valid']}")
    if wma["wma_details"]:
        print()
        print(f"  {'Name':<30} {'Acres':>10}  Counties")
        print(f"  {'-'*29:<30} {'-'*9:>10}  {'-'*25}")
        for w in sorted(wma["wma_details"], key=lambda x: x["acres"], reverse=True):
            print(f"  {w['name'][:30]:<30} {w['acres']:>10,}  {w['counties']}")

    # Summary
    print_section("Data Inventory Summary")
    sources_ok = 0
    total_sources = 3

    if s2["total_scenes"] > 0:
        sources_ok += 1
        print("  [OK] Sentinel-2 imagery:  available")
    else:
        print("  [--] Sentinel-2 imagery:  not found")

    if dem["tiles_found"] > 0:
        sources_ok += 1
        print("  [OK] Copernicus DEM:      available")
    else:
        print("  [--] Copernicus DEM:      not found")

    if wma["wmas_in_bbox"] > 0:
        sources_ok += 1
        print("  [OK] Protected areas:     available")
    else:
        print("  [--] Protected areas:     none in bbox")

    print()
    print(f"  Data completeness: {sources_ok}/{total_sources} sources available")

    if sources_ok == total_sources:
        print("  Assessment: Site has sufficient data for reforestation analysis.")
        print("  Next steps: Download imagery, build DEM mosaic, overlay boundaries.")
    else:
        missing = total_sources - sources_ok
        print(f"  Assessment: {missing} data source(s) missing — review alternatives.")

    print()
    print("  Full JSON report:")
    report_json = json.dumps(report, indent=2, default=str)
    for line in report_json.split("\n")[:30]:
        print(f"    {line}")
    print("    ...")
    print()
    print("Assessment complete.")


if __name__ == "__main__":
    asyncio.run(main())
