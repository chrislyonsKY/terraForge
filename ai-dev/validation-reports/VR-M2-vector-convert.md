# VR-M2-vector-convert — Vector Format Conversion Validation

**Date:** 2026-03-12
**Module:** `earthforge.vector.convert`
**Input:** ESRI Shapefile → GeoParquet 1.1.0

---

## Test Input

Synthetic KY cities Shapefile — 6 point features, EPSG:4326, fields: `name` (string), `pop` (integer).
Created via OGR to represent a realistic municipal dataset.

| City | Lon | Lat | Pop |
|------|-----|-----|-----|
| Lexington | -84.495 | 38.049 | 322,570 |
| Louisville | -85.759 | 38.254 | 633,045 |
| Bowling Green | -86.443 | 36.990 | 72,294 |
| Owensboro | -87.113 | 37.774 | 59,013 |
| Covington | -84.508 | 39.083 | 43,380 |
| Pikeville | -82.519 | 37.479 | 6,903 |

## Conversion Result

| Field | Value |
|-------|-------|
| Source format | ESRI Shapefile |
| Output format | geoparquet |
| Feature count | 6 |
| Geometry type | Point |
| CRS | EPSG:4326 |
| Bbox | [-87.113, 36.990, -82.519, 39.083] |
| Output file size | 3,011 bytes |

## GeoParquet Metadata Verified

- `geo` metadata written at Parquet file level
- `primary_column = "geometry"`
- `encoding = "WKB"`
- CRS stored as PROJJSON (converted from OGR WKT via `json.loads(srs.ExportToPROJJSON())`)
- `bbox` covering written per feature (enables row-group predicate pushdown in `query_features`)
- `geometry_types` set from OGR geometry type

## Roundtrip

Output GeoParquet is readable by `earthforge.vector.query.query_features` — confirmed by
the vector query validation test (VR-M2-vector-query.md).
