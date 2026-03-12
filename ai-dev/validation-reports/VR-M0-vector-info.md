# VR-M0-vector-info — Vector Info Validation

**Date:** 2026-03-12
**Module:** `earthforge.vector.info`
**Stage:** Milestone 0 — Foundation

---

## Test Input

GeoParquet file (4 KY city point features, EPSG:4326) produced by `earthforge.vector.convert`
from an ESRI Shapefile. GeoParquet 1.1.0 with WKB geometry encoding and PROJJSON CRS metadata.

| City | Lon | Lat |
|------|-----|-----|
| Lexington | -84.495 | 38.049 |
| Louisville | -85.759 | 38.254 |
| Bowling Green | -86.443 | 36.990 |
| Pikeville | -82.519 | 37.479 |

## Result

| Field | Value |
|-------|-------|
| Row count | 4 |
| Num columns | 2 (geometry, name) |
| CRS | EPSG:4326 |
| Bbox | [-86.443, 36.990, -82.519, 38.254] |
| Geometry types | ['Point'] |
| Compression | SNAPPY |
| File size | 2,681 bytes |
| Elapsed | 5.6ms |

## Notes

- `inspect_vector` reads Parquet metadata from the file footer — no row data is decoded.
  On large GeoParquet files (Overture Maps building partitions, ~1–5 GB), only the
  footer is fetched, making `info` instantaneous regardless of file size.
- CRS is read from the GeoParquet `geo` metadata as PROJJSON and normalized to
  `EPSG:4326` authority format.
- Bbox is the bounding box stored in the `geo` metadata, not computed from geometry
  — consistent with GeoParquet 1.1.0 spec.
