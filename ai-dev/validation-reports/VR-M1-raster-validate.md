# VR-M1-raster-validate — COG Validation Validation

**Date:** 2026-03-12
**Module:** `earthforge.raster.validate`
**Stage:** Milestone 1

---

## Valid COG (should pass all checks)

Input: 2048×2048 uint16 DEFLATE-compressed GeoTIFF converted via
`earthforge.raster.convert` with `blocksize=512`. Output validated immediately
after conversion.

| Check | Result | Detail |
|-------|--------|--------|
| `geotiff` | PASS | File is a GeoTIFF |
| `tiled` | PASS | Tiled layout (block=512×512) |
| `overviews` | PASS | Overviews present (levels=[2, 4]) |
| `compression` | PASS | Compressed (DEFLATE) |
| `ifd_order` | PASS | IFD ordering OK |
| **Overall** | **PASS** | `is_valid = True` |

## Non-COG GeoTIFF (should fail tiled + overviews)

Input: 512×512 uint8 strip GeoTIFF (no tiling, no overviews, no compression)
created directly with rasterio defaults.

| Check | Result | Detail |
|-------|--------|--------|
| `geotiff` | PASS | File is a GeoTIFF |
| `tiled` | FAIL | Strip layout — not tiled |
| `overviews` | FAIL | No overviews |
| `compression` | FAIL | Not compressed |
| `ifd_order` | PASS | IFD ordering OK (single IFD, trivially ordered) |
| **Overall** | **FAIL** | `is_valid = False` |

## Notes

- The `tiled` check reads `ds.profile.get("tiled", False)` to avoid the
  deprecated `rasterio.DatasetReader.is_tiled` property (changed in rasterio 1.3.4).
- The `ifd_order` check confirms the ghost/overview IFDs precede the full-resolution
  IFD in the file — this is required for range-read efficiency on remote COGs.
