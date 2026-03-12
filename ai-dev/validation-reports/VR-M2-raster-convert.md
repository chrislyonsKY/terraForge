# VR-M2-raster-convert — GeoTIFF to COG Conversion Validation

**Date:** 2026-03-12
**Module:** `earthforge.raster.convert`
**Validator:** `earthforge.raster.validate` (internal COG checker)

---

## Test Input

Synthetic 2048×2048 single-band GeoTIFF (uint16), EPSG:4326, KY bounding box (`-85, 37, -84, 38`).
Created with `rasterio` using a strip layout (no tiling, no overviews) to confirm the converter
produces a valid COG regardless of input layout.

## Conversion Parameters

| Parameter | Value |
|-----------|-------|
| Compression | DEFLATE |
| Blocksize | 512 |
| Resampling | nearest |
| Overview levels | auto-computed → [2, 4] |

## Conversion Result

| Field | Value |
|-------|-------|
| Dimensions | 2048×2048 |
| Band count | 1 |
| Dtype | uint16 |
| CRS | EPSG:4326 |
| Compression | deflate |
| Blocksize | 512 |
| Overview levels | [2, 4] |
| Output file size | 11,015,137 bytes (~10.5 MB) |

## Validation Result

| Check | Passed | Detail |
|-------|--------|--------|
| `geotiff` | ✅ | File is a GeoTIFF |
| `tiled` | ✅ | Tiled layout (block=512×512) |
| `overviews` | ✅ | Overviews present (levels=[2, 4]) |
| `compression` | ✅ | Compressed (DEFLATE) |
| `ifd_order` | ✅ | IFD ordering OK |
| **Overall** | ✅ **valid** | |

## Notes

- GDAL COG driver handles tile layout, IFD reordering, and overview generation in a single
  `gdal.Translate()` call — no intermediate strip file needed.
- Overview levels are auto-computed as powers of 2 until the smallest overview dimension
  approaches half a tile (512). For 2048×2048 this yields levels [2, 4].
- Conversion from strip GeoTIFF (no overviews) to valid COG confirmed.
