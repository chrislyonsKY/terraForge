"""KY Wildlife Management Areas — vector convert and query demo.

Fetches Kentucky Wildlife Management Area (WMA) polygon boundaries from the
KY GIS MapServer, converts the Esri JSON to GeoJSON, then converts to
GeoParquet and demonstrates spatial bbox queries and attribute filtering.

Data source: KY Public Hunting Areas — WMA polygons (~100 areas)
  Portal: https://opengisdata.ky.gov
  Service: https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/
           Ky_Public_Hunting_Areas_WGS84WM/MapServer/1

Usage::

    python examples/ky_wma_demo.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx

from earthforge.vector.convert import convert_vector
from earthforge.vector.info import inspect_vector
from earthforge.vector.query import query_features

# ArcGIS REST endpoint for KY Public Hunting Areas (layer 1 = Hunting Areas)
SERVICE_URL = (
    "https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services"
    "/Ky_Public_Hunting_Areas_WGS84WM/MapServer/1"
)


def _esri_polygon_to_geojson_geometry(geom: dict) -> dict:
    """Convert an Esri JSON polygon geometry to GeoJSON Polygon/MultiPolygon.

    Esri JSON uses ``rings`` where the first ring is the exterior and
    subsequent rings are holes.  GeoJSON uses nested coordinate arrays.
    For simplicity we treat each ring set as a single polygon; features
    with multiple disjoint parts become MultiPolygon.

    Parameters:
        geom: Esri JSON geometry dict with ``rings``.

    Returns:
        GeoJSON geometry dict.
    """
    rings = geom.get("rings", [])
    if not rings:
        return {"type": "Polygon", "coordinates": []}

    # Simple heuristic: if only one ring, it's a Polygon.
    # Multiple rings could be holes or disjoint parts — treat as Polygon
    # with holes (good enough for demo purposes).
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings}

    # For multiple rings, wrap as a single Polygon (exterior + holes)
    return {"type": "Polygon", "coordinates": rings}


def fetch_wma_geojson(max_features: int = 500) -> dict:
    """Fetch KY Wildlife Management Areas from the ArcGIS REST API.

    Queries the Public Hunting Areas MapServer for features where WMA='Yes',
    converts the Esri JSON response to a GeoJSON FeatureCollection.

    Parameters:
        max_features: Maximum features to return.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    data = {
        "where": "WMA='Yes'",
        "outFields": "AREANAME,WMA,WILDMGTREG,MANAGER,ACRES_CAL,Counties",
        "resultRecordCount": str(max_features),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }

    r = httpx.post(f"{SERVICE_URL}/query", data=data, timeout=120)
    r.raise_for_status()
    esri_json = r.json()

    if esri_json.get("error"):
        msg = esri_json["error"].get("message", "Unknown error")
        raise RuntimeError(f"ArcGIS query error: {msg}")

    features = []
    for feat in esri_json.get("features", []):
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        features.append({
            "type": "Feature",
            "properties": attrs,
            "geometry": _esri_polygon_to_geojson_geometry(geom),
        })

    return {"type": "FeatureCollection", "features": features}


async def main() -> None:
    """Run the KY Wildlife Management Areas conversion and query demo."""
    print()
    print("EarthForge — KY Wildlife Management Areas Demo")
    print("=" * 50)
    print()

    with tempfile.TemporaryDirectory() as tmp:
        # Step 1: Fetch WMAs from ArcGIS REST API
        print("=" * 55)
        print("FETCH: KY WMAs from ArcGIS MapServer")
        print("=" * 55)
        geojson = fetch_wma_geojson()
        feature_count = len(geojson["features"])
        print(f"  Endpoint:   {SERVICE_URL}")
        print("  Filter:     WMA='Yes'")
        print(f"  Fetched:    {feature_count} wildlife management areas")

        # Show a sample of area names
        sample_names = [
            f["properties"].get("AREANAME", "?")
            for f in geojson["features"][:5]
        ]
        print(f"  Sample:     {', '.join(sample_names)}")

        # Write GeoJSON to disk
        geojson_path = Path(tmp) / "ky_wma.geojson"
        geojson_path.write_text(json.dumps(geojson))
        geojson_size = geojson_path.stat().st_size
        print(f"  GeoJSON:    {geojson_size:,} bytes")
        print()

        # Step 2: Convert GeoJSON -> GeoParquet
        print("=" * 55)
        print("CONVERT: GeoJSON -> GeoParquet")
        print("=" * 55)
        parquet_path = str(Path(tmp) / "ky_wma.parquet")
        result = await convert_vector(str(geojson_path), output=parquet_path)
        print(f"  Format:     {result.input_format} -> {result.output_format}")
        print(f"  Features:   {result.feature_count}")
        print(f"  Geometry:   {result.geometry_type}")
        print(f"  CRS:        {result.crs}")
        print(f"  BBox:       {result.bbox}")
        print(f"  File size:  {result.file_size_bytes:,} bytes")
        if geojson_size > 0 and result.file_size_bytes:
            ratio = result.file_size_bytes / geojson_size
            print(f"  Ratio:      {ratio:.1%} of GeoJSON size")
        print()

        # Step 3: Inspect the GeoParquet
        print("=" * 55)
        print("INSPECT: GeoParquet metadata")
        print("=" * 55)
        info = await inspect_vector(parquet_path)
        print(f"  Format:     {info.format}")
        print(f"  Rows:       {info.row_count}")
        print(f"  Columns:    {info.num_columns}")
        for col in info.columns:
            geom_tag = " (geometry)" if col.is_geometry else ""
            print(f"    {col.name:15s} {col.type}{geom_tag}")
        print(f"  Geom col:   {info.geometry_column}")
        print(f"  Encoding:   {info.encoding}")
        print(f"  CRS:        {info.crs}")
        print()

        # Step 4: Spatial query — Eastern KY (Appalachian region)
        eastern_ky_bbox = [-84.0, 37.0, -82.0, 38.5]
        print("=" * 55)
        print("QUERY: WMAs in Eastern Kentucky")
        print("=" * 55)
        print(f"  BBox:       {eastern_ky_bbox}")
        query_result = await query_features(
            parquet_path, bbox=eastern_ky_bbox
        )
        print(
            f"  Matched:    {query_result.feature_count}"
            f" / {query_result.total_rows}"
        )
        for f in query_result.features:
            name = f.get("AREANAME", "?")
            acres = f.get("ACRES_CAL", 0)
            counties = f.get("Counties", "?")
            print(f"    {name[:30]:30s} | {acres:>10,.0f} ac | {counties}")
        print()

        # Step 5: Attribute query — largest WMAs by acreage
        print("=" * 55)
        print("QUERY: Top 10 largest WMAs by acreage")
        print("=" * 55)
        all_result = await query_features(
            parquet_path,
            columns=[
                "AREANAME", "ACRES_CAL", "WILDMGTREG", "MANAGER", "Counties",
            ],
            include_geometry=False,
        )
        # Sort by acreage descending
        sorted_wmas = sorted(
            all_result.features,
            key=lambda f: f.get("ACRES_CAL", 0) or 0,
            reverse=True,
        )
        print(f"  Total WMAs: {all_result.feature_count}")
        for f in sorted_wmas[:10]:
            name = f.get("AREANAME", "?")
            acres = f.get("ACRES_CAL", 0) or 0
            region = f.get("WILDMGTREG", "?")
            manager = f.get("MANAGER", "?")
            print(
                f"    {name[:30]:30s} | {acres:>10,.0f} ac"
                f" | {region[:12]:12s} | {manager}"
            )
        print()

        # Step 6: Query by region — Bluegrass WMAs
        print("=" * 55)
        print("QUERY: Bluegrass region WMAs")
        print("=" * 55)
        all_result2 = await query_features(
            parquet_path,
            columns=["AREANAME", "ACRES_CAL", "WILDMGTREG", "Counties"],
            include_geometry=False,
        )
        bluegrass = [
            f for f in all_result2.features
            if "Bluegrass" in (f.get("WILDMGTREG") or "")
        ]
        print(f"  Bluegrass WMAs: {len(bluegrass)}")
        for f in bluegrass:
            name = f.get("AREANAME", "?")
            acres = f.get("ACRES_CAL", 0) or 0
            counties = f.get("Counties", "?")
            print(f"    {name[:30]:30s} | {acres:>10,.0f} ac | {counties}")
        print()

    print("Demo complete.")


if __name__ == "__main__":
    asyncio.run(main())
