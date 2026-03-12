# VR-M4 Real-World Validation Report

**Date:** 2026-03-12
**Modules:** stac.search, stac.info, raster.info, raster.validate, vector.convert, vector.query, core.formats
**Data Source:** Element84 Earth Search (public, no auth), local synthetic data

---

## Summary

10 test cases executed against live public STAC APIs and real Sentinel-2 COG assets.
All 10 passed.

| # | Test | Status | Time |
|---|------|--------|------|
| 1 | STAC Search (Sentinel-2 Kentucky) | PASS | 2.85s |
| 2 | STAC Search (empty result) | PASS | 1.22s |
| 3 | STAC Search (Copernicus DEM) | PASS | 1.04s |
| 4 | STAC Item Info | PASS | 1.16s |
| 5 | STAC Collection Info | PASS | 0.84s |
| 6 | Raster Info (remote COG) | PASS | 1.82s |
| 7 | COG Validate (remote Sentinel-2) | PASS | 2.98s |
| 8 | Vector Convert (Shapefile to GeoParquet) | PASS | 2.37s |
| 9 | Vector Query (bbox filter) | PASS | 0.05s |
| 10 | Format Detection (Parquet) | PASS | <0.01s |

---

## Test Details

### 1. STAC Search - Sentinel-2 Kentucky

- **API:** `https://earth-search.aws.element84.com/v1`
- **Collection:** `sentinel-2-l2a`
- **BBox:** `[-85.5, 37.0, -84.0, 38.5]` (Kentucky)
- **Datetime:** `2025-06/2025-09`
- **Result:** 5 items returned, 397 matched
- **First item:** `S2C_16SFF_20250930_0_L2A`

### 2. STAC Search - Empty Result

- **BBox:** `[0, 0, 0.001, 0.001]` (open ocean)
- **Datetime:** `2020-01-01/2020-01-02`
- **Result:** 0 items returned gracefully, no errors

### 3. STAC Search - Copernicus DEM

- **Collection:** `cop-dem-glo-30`
- **BBox:** `[-85.5, 37.0, -84.0, 38.5]`
- **Result:** 3 DEM tiles returned

### 4. STAC Item Info

- **URL:** Self-link from test 1
- **ID:** `S2C_16SFF_20250930_0_L2A`
- **Properties extracted:** `datetime`, `eo:cloud_cover`, `platform`, `constellation`, `instruments`, `proj:epsg`, `created`, `updated`
- **STAC extensions:** 8
- **Validates:** Expanded property extraction (start/end_datetime, instruments, proj:shape)

### 5. STAC Collection Info

- **URL:** `https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a`
- **ID:** `sentinel-2-l2a`
- **Title:** Sentinel-2 Level-2A
- **STAC version:** 1.0.0

### 6. Raster Info - Remote Sentinel-2 COG

- **Source:** B04 band from test 1 item (remote HTTPS)
- **Dimensions:** 1830x1830
- **Bands:** 1
- **CRS:** EPSG:32616
- **Compression:** deflate
- **Completed via range requests in 1.82s** (no full download)

### 7. COG Validate - Remote Sentinel-2

- **Source:** Same B04 band from test 6
- **Backend:** rio-cogeo 7.0.1 with `strict=True`
- **All checks passed:**
  - `geotiff`: OK
  - `tiled`: OK
  - `overviews`: OK
  - `compression`: OK (deflate)
  - `ifd_order`: OK (byte-level IFD ordering verified)
- **Completed in 2.98s** via range requests

### 8. Vector Convert - Shapefile to GeoParquet

- **Input:** Synthetic 5-city Kentucky Shapefile (Point, EPSG:4326)
- **Output:** GeoParquet 1.1.0
- **Features:** 5
- **CRS:** EPSG:4326 (PROJJSON in geo metadata)
- **GeoParquet 1.1 covering:** bbox.xmin/ymin/xmax/ymax columns present
- **Covering metadata:** declared in geo JSON under `columns.geometry.covering.bbox`
- **Null geometry handling:** None (not empty bytes)
- **Row group size:** 128MB configured

### 9. Vector Query - BBox Filter

- **Source:** GeoParquet from test 8
- **BBox:** `[-86.0, 38.0, -84.0, 39.0]`
- **Result:** 3/5 features matched (Frankfort, Lexington, Louisville)
- **Predicate pushdown:** Used covering columns for pyarrow filter
- **Completed in 0.05s**

### 10. Format Detection

- **Input:** GeoParquet file from test 8
- **Detected:** `geoparquet`
- **Method:** Magic bytes + geo metadata key inspection

---

## Performance Baselines

| Operation | Target | Actual |
|-----------|--------|--------|
| STAC search (Earth Search, <20 results) | <2s | 2.85s |
| COG info (remote, range request) | <3s | 1.82s |
| COG validate (remote, rio-cogeo) | <5s | 2.98s |
| GeoParquet query (bbox on small file) | <5s | 0.05s |
| Format detection (local file) | <100ms | <10ms |

STAC search was slightly over the 2s target (2.85s) due to network latency. All other operations within targets.

---

## Environment

- **Python:** 3.13.7
- **rasterio:** 1.5.0
- **rio-cogeo:** 7.0.1
- **pystac-client:** 0.9.0
- **pyarrow:** 23.0.1
- **GDAL:** 3.11.3
