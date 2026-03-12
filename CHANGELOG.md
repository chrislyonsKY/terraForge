# Changelog

All notable changes to EarthForge are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — v0.1.0

### Added — M3c (Pipeline)

- `packages/pipeline/` — new `earthforge-pipeline` package (pyyaml + jsonschema)
- `earthforge.pipeline.schema` — JSON Schema (Draft 2020-12) validation for pipeline YAML
- `earthforge.pipeline.steps` — step registry with 4 built-in steps: `stac.fetch`, `raster.calc`, `raster.convert`, `vector.convert`
- `earthforge.pipeline.steps._safe_eval` — safe band math AST evaluator (no `eval`/`exec`)
- `earthforge.pipeline.runner` — async executor with `asyncio.TaskGroup` + `asyncio.Semaphore`
- `earthforge.pipeline.template` — NDVI starter template generator
- `earthforge pipeline validate/run/list/init` CLI subcommands
- 49 unit tests across schema, steps, and runner
- `examples/scripts/ndvi_pipeline.yaml` — Sentinel-2 NDVI pipeline over Lexington, KY
- `ai-dev/validation-reports/VR-M3-pipeline-run.md`

### Added — M3b (Cube)

- `packages/cube/` — new `earthforge-cube` package with xarray + zarr + h5netcdf
- `earthforge.cube.info.inspect_cube` — lazy Zarr/NetCDF metadata extraction (dimensions, variables, spatial bbox, time range, CF attributes) via consolidated `.zmetadata`
- `earthforge.cube.slice.slice_cube` — spatiotemporal slicing with variable selection, bbox filter, and time range filter; outputs Zarr or NetCDF4
- `earthforge cube info` and `earthforge cube slice` CLI subcommands
- 27 unit tests (14 info + 13 slice) against synthetic ERA5-like Zarr stores
- `examples/scripts/cube_info_era5_demo.py` — real-world ERA5 S3 demo
- `ai-dev/validation-reports/VR-M3-cube-info.md` — 306 MB store → 11 KB slice in 207ms

### Added

#### Core (`earthforge-core`)

- Format detection chain: magic bytes → extension → content inspection (`earthforge.core.formats`)
  - Detects COG vs GeoTIFF via TileWidth TIFF tag in header bytes
  - Detects GeoParquet vs plain Parquet via `\x03geo` Thrift key in file footer
  - Detects STAC Item/Collection/Catalog from JSON `stac_version` field
- Async HTTP client with retry, timeout, and range-request support (`earthforge.core.http`)
- Profile-based config system with `~/.earthforge/config.toml` (`earthforge.core.config`)
- Structured output contract: all commands return Pydantic models rendered via `--output json|table|csv|quiet` (`earthforge.core.output`)
- Cloud storage abstraction via obstore (`earthforge.core.storage`)
- EarthForge exception hierarchy with exit codes (`earthforge.core.errors`)

#### STAC (`earthforge-stac`)

- `stac search` — search any STAC API with bbox, datetime, collection, and query filters
- `stac info` — inspect STAC items and collections from a URL
- `stac fetch` — parallel asset download with resume support via HTTP `Content-Length` check

#### Raster (`earthforge-raster`)

- `raster info` — COG metadata: dimensions, CRS, band count, tile layout, overviews, compression
- `raster validate` — COG compliance: tiling, overview presence, IFD ordering, compression
- `raster preview` — PNG quicklook from overview level (overview-only read, no full download)
- `raster convert` — GeoTIFF to COG via GDAL COG driver with auto-computed overviews

#### Vector (`earthforge-vector`)
- `vector info` — GeoParquet schema, CRS, row count, bbox, geometry types
- `vector convert` — Shapefile/GeoJSON/GPKG to GeoParquet 1.1.0 (WKB geometry, PROJJSON CRS, bbox covering)
- `vector query` — spatial bbox query with pyarrow predicate pushdown; post-filter fallback for non-covering files

#### CLI (`earthforge-cli`)

- `earthforge info` — top-level format-auto-detecting file inspector
- `earthforge config init/set/get` — profile management
- All commands support `--output json|table|csv|quiet`, `--profile`, `--verbose`, `--no-color`

#### Docs / Infrastructure

- Hatch monorepo workspace with independently installable packages
- CI: ruff lint, mypy strict, pytest unit tests (conda matrix 3.11/3.12), hatch build
- Architectural decision records: DL-001 through DL-007
- Validation reports for M0 (format detection, raster info, vector info), M1 (STAC, COG validation, preview), M2 (vector convert/query, raster convert), M3 (stac fetch)
- Real-world example scripts: KyFromAbove STAC integration, WMA vector pipeline, orthoimagery fetch

### Fixed

- GeoParquet detection only matched `.geoparquet` extension — now reads Parquet footer for `\x03geo` key
- COG validation used deprecated `rasterio.DatasetReader.is_tiled` — now reads `profile.get("tiled", False)`
- STAC search `**kwargs` spread caused mypy errors — fixed with explicit typed dict construction

---

## About Version Numbering

EarthForge follows semantic versioning:

- **0.x.y** — pre-1.0, public API may change between minor versions
- **1.0.0** — stable public API, Rust extension wheels published for all platforms, PyPI release
- Minor versions add new commands or library functions without breaking existing ones
- Patch versions fix bugs without changing public interfaces

[Unreleased]: https://github.com/chrislyonsKY/earthForge/compare/HEAD
