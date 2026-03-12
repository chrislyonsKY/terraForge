# VR-M0-raster-info — Raster Info Validation

**Date:** 2026-03-12
**Module:** `earthforge.raster.info`
**Stage:** Milestone 0 — Foundation

---

## Test Input

Synthetic 2048×2048 3-band uint16 GeoTIFF in UTM Zone 17N (EPSG:32617), simulating a
Sentinel-2 tile footprint (`300000, 4200000, 400000, 4300000`). Tiled layout
(512×512 blocks), no overviews, no compression (raw TIFF).

## Result

| Field | Value |
|-------|-------|
| Dimensions | 2048×2048 |
| Band count | 3 |
| Band dtype | uint16 |
| CRS | EPSG:32617 |
| Bounds | [300000.0, 4200000.0, 400000.0, 4300000.0] |
| Is tiled | True |
| Block size | 512×512 |
| Overview count | 0 |
| Compression | None |
| Interleave | pixel |
| Elapsed | 43.2ms |

## Notes

- `inspect_raster` reads only the file header via rasterio — no full pixel data
  is loaded into memory. On a real remote COG, only a few HTTP range requests
  would be needed for the IFD + first tile header.
- The 43ms elapsed is dominated by creating a rasterio dataset object locally.
  For cloud files the network latency would dominate, but the read pattern
  (IFD → header → metadata only) is unchanged.
- Overview count = 0 because the test file was created without `--co OVERVIEWS`.
  Real Sentinel-2 COGs from Earth Search have overview levels [2, 4, 8, 16].
