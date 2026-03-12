# VR-M0-format-detection — Format Detection Validation

**Date:** 2026-03-12
**Module:** `earthforge.core.formats`
**Stage:** Milestone 0 — Foundation

---

## Detection Chain

`detect()` uses a three-stage chain:
1. **Magic bytes** — first 4 bytes matched against known signatures
2. **Extension fallback** — if no magic match, check file extension
3. **Content inspection** — registered inspectors refine ambiguous candidates

## Test Matrix

| Format | File | Expected | Detected | Time | Result |
|--------|------|----------|----------|------|--------|
| Strip GeoTIFF (no tile) | `strip.tif` | `geotiff` | `geotiff` | 0.9ms | PASS |
| Tiled GeoTIFF / COG | `cog.tif` (512×512 tiles) | `cog` | `cog` | 5.8ms | PASS |
| GeoParquet 1.1.0 | `pts.parquet` | `geoparquet` | `geoparquet` | 0.7ms | PASS |
| Plain Parquet (no geo) | `plain.parquet` | `parquet` | `parquet` | 0.6ms | PASS |
| GeoJSON FeatureCollection | `pts.geojson` | `geojson` | `geojson` | 0.3ms | PASS |

## Key Disambiguation Cases

### GeoTIFF vs COG
Magic bytes match `TIFF` for both. The `_inspect_tiff_for_cog` inspector scans the
512-byte header for TIFF tag 322 (`TileWidth`, encoded as `\x42\x01` little-endian).
Presence → `COG`. Absence → `GEOTIFF`.

### GeoParquet vs plain Parquet
Both share `PAR1` magic bytes. The `_inspect_parquet_for_geo` inspector reads the
last 4 KB of local files and searches for `\x03geo` — the Thrift compact encoding
of a 3-character string key "geo" in the Parquet key-value metadata. Plain Parquet
files do not contain this key.

Note: `\x03geo` could coincidentally appear in a non-GeoParquet Parquet file if a
user-defined key of length 3 happened to be "geo". This is acceptable — the full
GeoParquet validator in `earthforge.vector.validate` performs schema-level checks.

## Performance Baselines

All local detections complete in <10ms. Remote URL detection (not tested here) fetches
only the first 512 bytes via HTTP Range request, which is sufficient for magic-byte
matching. GeoParquet from remote URLs falls back to extension detection.

| Target | Achieved |
|--------|----------|
| <100ms local | Yes — all <6ms |

## Bug Fixed During Validation

Prior to this validation, `_inspect_parquet_for_geo` only checked the filename for
"geoparquet" — it never detected GeoParquet files named `*.parquet`. Fixed by
adding a footer read with `\x03geo` key detection.
