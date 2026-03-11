# Real-World Test Data Plan

Every EarthForge feature must be validated against real-world data before it ships. This document lists the specific public datasets, exact URLs, and expected results for each feature. The results must be recorded in `ai-dev/validation-reports/`.

---

## STAC APIs

### Element84 Earth Search (Public, No Auth)

| Property | Value |
|---|---|
| API URL | `https://earth-search.aws.element84.com/v1` |
| Collections | sentinel-2-l2a, sentinel-2-c1-l2a, landsat-c2-l2, sentinel-1-grd, cop-dem-glo-30, cop-dem-glo-90, naip |
| Auth | None required |
| Use for | STAC search, item info, collection info, asset fetch |

**Test searches:**

- `sentinel-2-l2a`, bbox `(-85.5, 37.0, -84.0, 38.5)` (Kentucky), datetime `2025-06/2025-09` — should return multiple items
- `sentinel-2-l2a`, bbox `(-85.5, 37.0, -84.0, 38.5)`, cloud cover <20% — should return fewer items than unfiltered
- `cop-dem-glo-30`, bbox `(-85.5, 37.0, -84.0, 38.5)` — should return DEM tiles
- Search with no results: `sentinel-2-l2a`, bbox `(0, 0, 0.001, 0.001)`, datetime `2020-01-01/2020-01-02` — should return empty result set gracefully

### Planetary Computer (Public, SAS Token Required)

| Property | Value |
|---|---|
| API URL | `https://planetarycomputer.microsoft.com/api/stac/v1` |
| Token endpoint | `https://planetarycomputer.microsoft.com/api/sas/v1/token` |
| Collections | sentinel-2-l2a, landsat-c2-l2, naip, cop-dem-glo-30 |
| Auth | SAS token auto-signed via planetary-computer package or manual token endpoint |
| Use for | STAC search with auth, profile-based config validation |

**Test searches:**

- `sentinel-2-l2a`, bbox `(-85.5, 37.0, -84.0, 38.5)`, datetime `2025-06/2025-09` — should return items with Azure blob asset URLs
- Verify SAS token signing works for asset URLs

---

## COG (Cloud Optimized GeoTIFF)

### Sentinel-2 COGs on S3 (Valid COGs)

| Property | Value |
|---|---|
| Example asset | `https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/T/YM/2023/9/S2A_18TYM_20230926_0_L2A/B04.tif` |
| Access | Public, no auth |
| Expected format | COG — tiled, with overviews, deflate or JPEG2000 compression |
| Size | ~50-150MB per band |

**Tests for `earthforge raster info`:**

- Should report: tiled=true, overview_count > 0, CRS (EPSG:32618 or UTM zone), band count, dimensions, compression
- Should complete in <3 seconds via range requests (not full download)

**Tests for `earthforge raster preview`:**

- Should generate a PNG quicklook from overview level
- Should transfer <5MB of data for a ~100MB COG

**Tests for `earthforge raster validate`:**

- Sentinel-2 COGs should pass validation (tiled, overviews present, correct IFD ordering)

### Copernicus DEM COGs (Valid COGs, Different Structure)

| Property | Value |
|---|---|
| Source | Search via Earth Search `cop-dem-glo-30` collection |
| Expected format | COG — single band, float32, elevation data |
| Use for | Testing info/validate against non-imagery COGs |

### Non-COG GeoTIFF (Expected Failure)

To validate that `earthforge raster validate` correctly identifies non-COGs, create or obtain a stripped (non-tiled) GeoTIFF without overviews. The validate command should report warnings: "Not tiled", "No overviews."

---

## GeoParquet

### Overture Maps Buildings (Large-Scale Real GeoParquet)

| Property | Value |
|---|---|
| S3 path | `s3://overturemaps-us-west-2/release/{latest}/theme=buildings/type=building/` |
| STAC catalog | `https://stac.overturemaps.org/catalog.json` |
| Format | GeoParquet 1.1 with bbox struct, WKB geometry, zstd compression |
| Size | Individual partitions ~50-200MB, total dataset ~110GB |
| Auth | Public, no auth |

**Tests for `earthforge vector info`:**

- Should report: geometry column, CRS, geometry types (MultiPolygon), feature count, bbox, row group count
- Should detect `geo` metadata key in Parquet metadata

**Tests for `earthforge vector query`:**

- Query with bbox `(-85.5, 37.0, -84.0, 38.5)` (Kentucky) should return buildings
- Verify predicate pushdown: query should NOT read all row groups (measure data transferred vs. file size)

**Tests for `earthforge vector validate`:**

- Overture files should pass GeoParquet validation (geo metadata present, CRS in PROJJSON, geometry column declared)

### source.coop Datasets (Smaller GeoParquet)

| Property | Value |
|---|---|
| URL | Browse `https://source.coop` for smaller GeoParquet datasets |
| Use for | Testing with manageable file sizes during development |

---

## Zarr

### ERA5 Climate Data on Planetary Computer (Real Zarr Store)

| Property | Value |
|---|---|
| Catalog | `https://planetarycomputer.microsoft.com/api/stac/v1/collections/era5-pds` |
| Format | Zarr v2 with consolidated metadata |
| Variables | temperature, pressure, precipitation, etc. |
| Dimensions | time, latitude, longitude |

**Tests for `earthforge cube info`:**

- Should report: dimensions (time, latitude, longitude), variables, chunk sizes, CF-convention metadata
- Should complete without downloading the full dataset (lazy open via consolidated metadata)

**Tests for `earthforge cube slice`:**

- Spatiotemporal slice: time `2025-06`, bbox `(-85.5, 37.0, -84.0, 38.5)` — should return a subset without downloading full dataset
- Verify lazy loading: `xr.open_zarr()` should NOT trigger data transfer; only `.load()` on the slice should

---

## Format Detection

### Universal `earthforge info` Auto-Detection Tests

| Input | Expected Detection | Notes |
|---|---|---|
| Sentinel-2 COG (remote HTTPS URL) | `FormatType.COG` | Tiled TIFF with overviews |
| Stripped GeoTIFF (local file) | `FormatType.GEOTIFF` | TIFF magic bytes but no tiling/overviews |
| Overture building partition (S3 URL) | `FormatType.GEOPARQUET` | Parquet magic bytes + geo metadata |
| Plain Parquet without geo metadata | `FormatType.PARQUET` | Parquet magic bytes, no geo key |
| Zarr store (directory or S3 prefix) | `FormatType.ZARR` | Directory with `.zarray`/`.zmetadata` |
| STAC item JSON (HTTPS URL) | `FormatType.STAC_ITEM` | JSON with `"type": "Feature"` and STAC fields |
| STAC collection JSON | `FormatType.STAC_COLLECTION` | JSON with `"type": "Collection"` |
| GeoJSON file | `FormatType.GEOJSON` | JSON with `"type": "FeatureCollection"` or `"type": "Feature"` without STAC fields |
| Random non-geospatial file | `FormatType.UNKNOWN` | Should not crash — return unknown gracefully |

---

## Format Conversion

### Conversion Output Validation

All conversion outputs must be validated by third-party tools, not just by EarthForge's own validators:

| Conversion | Validation Tool | Expected Result |
|---|---|---|
| GeoTIFF → COG | `rio cogeo validate` | Valid COG, no warnings |
| Shapefile → GeoParquet | `gpq validate` or `geopandas.read_parquet()` | Valid GeoParquet with geo metadata and CRS |
| NetCDF → Zarr | `xarray.open_zarr()` | Opens successfully with correct dimensions/variables |
| GeoParquet → FlatGeobuf | `ogrinfo` | Valid FlatGeobuf with CRS and spatial index |

---

## Pipeline Execution

### End-to-End Pipeline Test

The pipeline runner must complete a real STAC → process → export workflow:

```yaml
pipeline:
  name: validation-test-ndvi
  source:
    stac_search:
      api: https://earth-search.aws.element84.com/v1
      collection: sentinel-2-l2a
      bbox: [-85.5, 37.0, -84.0, 38.5]
      datetime: "2025-06-01/2025-06-30"
      query:
        eo:cloud_cover: { lt: 20 }
      limit: 3
  steps:
    - for_each_item:
        - raster.calc:
            expression: "(B08 - B04) / (B08 + B04)"
            output: ndvi_{item_id}.tif
        - raster.convert:
            format: COG
            compression: deflate
```

**Expected result:** 3 NDVI COGs produced, each passing `rio cogeo validate`.

---

## Performance Baselines

Record these timing observations in validation reports to establish baselines:

| Operation | Target | Measurement |
|---|---|---|
| STAC search (Earth Search, <20 results) | <2 seconds | Wall clock time |
| COG info (remote, range request) | <3 seconds | Wall clock time |
| COG preview (remote, overview read) | <5 seconds | Wall clock time + bytes transferred |
| GeoParquet query (bbox on 100MB file) | <5 seconds | Wall clock time + row groups read vs. total |
| Zarr info (consolidated metadata) | <3 seconds | Wall clock time |
| Format detection (local file) | <100ms | Wall clock time |
| Format detection (remote file) | <2 seconds | Wall clock time (single range request for magic bytes) |
