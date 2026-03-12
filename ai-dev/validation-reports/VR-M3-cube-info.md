# VR-M3-cube-info — Cube Info/Slice Validation

**Date:** 2026-03-12
**Module:** `earthforge.cube.info`, `earthforge.cube.slice`
**Stage:** Milestone 3b

---

## Test Dataset

Synthetic ERA5-like Zarr store: 2 variables (`air_temperature_at_2_metres`,
`surface_pressure`), global 1-degree grid (181 × 361 cells), 744 hourly time
steps (January 2025). Written with `xarray.to_zarr` and consolidated metadata.

| Property | Value |
|---|---|
| Store format | Zarr (consolidated metadata) |
| Store size on disk | 306,651,761 bytes (307 MB) |
| Variables | 2 (float32) |
| Dimensions | time (744), latitude (181), longitude (361) |
| Grid | Global 1-degree, WGS84 |
| Conventions | CF-1.6 |

---

## Test: `inspect_cube` — Metadata Extraction

No data arrays were loaded. Only the consolidated `.zmetadata` was read.

| Field | Result | Expected |
|---|---|---|
| Format | `zarr` | `zarr` |
| Spatial bbox | `[-180.0, -90.0, 180.0, 90.0]` | Global extent |
| Time range | `2025-01-01T00:00:00 / 2025-01-31T23:00:00` | Jan 2025 |
| Dimension count | 3 (time, latitude, longitude) | 3 |
| Variable count | 2 | 2 |
| Variable dtypes | float32 | float32 |
| Variable shapes | [744, 181, 361] | [744, 181, 361] |
| CF units extracted | `K`, `Pa` | PASS |
| long_name extracted | `2 metre temperature` | PASS |

**Result: PASS**

---

## Test: `slice_cube` — Spatiotemporal Slicing

Slice: variable `air_temperature_at_2_metres`, bbox `(-85.5, 37.0, -84.0, 38.5)`
(Kentucky), time range `2025-01-01/2025-01-07` (first 7 days, 168 hourly steps).

| Field | Result |
|---|---|
| Output format | Zarr |
| Output size | 11,614 bytes (11 KB vs 153 MB single-variable full store) |
| Output shape | time=168, latitude=2, longitude=2 |
| Elapsed | 0.207s |
| Bbox recorded | `[-85.5, 37.0, -84.0, 38.5]` |
| Time range recorded | `['2025-01-01', '2025-01-07']` |

Reduction ratio: 153 MB → 11 KB (99.99% smaller) — only the chunks
intersecting the Kentucky bbox and first-week time range were loaded.

**Result: PASS**

---

## Unit Test Results

```
packages/cube/tests/test_cube_info.py    14 passed, 2 skipped (h5netcdf not in env)
packages/cube/tests/test_cube_slice.py   13 passed, 1 skipped (h5netcdf not in env)
```

Skipped tests are `test_basic_netcdf` and `test_netcdf_output_written` — both
use `pytest.importorskip("h5netcdf")` and will run in the CI conda environment
where `h5netcdf` is available.

---

## Notes

- zarr 3.0.8 emits a `UserWarning` about consolidated metadata not being part
  of the Zarr Format 3 specification. This is expected; the warning is benign
  and xarray handles it correctly. A filterwarnings entry should be added to
  `pytest.ini` or `pyproject.toml` for CI cleanliness.
- The 1-degree grid returns only 2 latitude and 2 longitude points for the KY
  bbox (`-85.5 to -84.0 lon`, `37.0 to 38.5 lat`). Higher-resolution grids
  (e.g. 0.25-degree ERA5) would return more points per bbox.
- Remote store validation (real `s3://era5-pds` bucket) deferred until CI
  environment has `s3fs` installed and AWS credential chain configured.
