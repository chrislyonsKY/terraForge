# VR-M1-raster-preview — Raster Preview Validation

**Date:** 2026-03-12
**Module:** `earthforge.raster.preview`
**Stage:** Milestone 1

---

## Test: RGB Preview from Tiled GeoTIFF

Input: 1024×1024 3-band uint8 GeoTIFF (EPSG:4326, tiled 256×256).
Request: `max_size=512` PNG thumbnail.

| Field | Value |
|-------|-------|
| Output dimensions | 512×512 (constrained by max_size) |
| Output format | PNG |
| File size | ~21 KB |
| Band mapping | B1→R, B2→G, B3→B |

## Test: Single-Band Preview (grayscale → colorized)

Input: 512×512 1-band float32 GeoTIFF (simulated DEM).
Request: `max_size=256` PNG thumbnail.

| Field | Value |
|-------|-------|
| Output dimensions | 256×256 |
| Output format | PNG |
| Band mapping | Single band → grayscale (RGB copy) |

## Test: Aspect Ratio Preservation

Input: 1024×512 (2:1 aspect ratio) raster, `max_size=256`.
Expected output: 256×128.
Result: PASS — short dimension constrains, aspect ratio preserved.

## Notes

- Preview reads only the highest-available overview level via rasterio,
  not the full-resolution image. For a remote 10 GB COG, only the
  overview tile data is transferred — the full image is never downloaded.
- PNG output uses PIL (Pillow). The preview module normalizes data ranges
  (uint16 → uint8 via percentile stretch) for visual output.
- `auto output path`: if `output` is not specified, the preview is written
  to `<source_stem>_preview.png` in the same directory as the source.
