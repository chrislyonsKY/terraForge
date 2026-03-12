# Release Notes

## v0.1.0 — Unreleased

### Added — M4 (Polish)

- `earthforge explore` — interactive full-screen STAC browser (Textual TUI)
- `earthforge completions bash|zsh|fish` — shell completion script generation
- `earthforge bench vector-query` — GeoParquet predicate pushdown vs full scan benchmark
- `earthforge bench raster-info` — COG header range-request timing benchmark
- PyPI publish workflow with OIDC trusted publishing (no stored tokens)

### Added — M3 (Pipeline + Cube)

- `earthforge pipeline validate/run/list/init` — declarative YAML pipeline executor
- Pipeline step registry: `stac.fetch`, `raster.calc`, `raster.convert`, `vector.convert`
- Safe band math AST evaluator (no `eval`/`exec`)
- `earthforge cube info` — lazy Zarr/NetCDF metadata (dimensions, variables, spatial bbox, time range)
- `earthforge cube slice` — spatiotemporal subset extraction without full download
- `earthforge stac fetch` — parallel asset download with resume support

### Added — M2 (Vector + Conversion)

- `earthforge vector info` — GeoParquet schema, CRS, feature count, bbox, geometry types
- `earthforge vector convert` — Shapefile/GeoJSON/GPKG → GeoParquet 1.1.0 with bbox covering column
- `earthforge vector query` — spatial bbox query with pyarrow predicate pushdown
- `earthforge raster convert` — GeoTIFF → COG via GDAL COG driver with auto overviews

### Added — M1 (STAC + Raster)

- `earthforge stac search` — search any STAC API with bbox, datetime, and collection filters
- `earthforge stac info` — inspect STAC items and collections from a URL
- `earthforge raster info` — COG metadata via HTTP range requests (no full download)
- `earthforge raster preview` — PNG quicklook from overview level
- `earthforge raster validate` — COG compliance check (tiling, overviews, IFD order)
- `earthforge config init/set/get` — profile management

### Added — M0 (Foundation)

- Format detection chain: magic bytes → extension → content inspection
  - Detects COG vs plain GeoTIFF via TileWidth TIFF tag
  - Detects GeoParquet vs plain Parquet via `\x03geo` footer key
  - Detects STAC Item/Collection/Catalog from JSON `stac_version` field
- Async HTTP client with retry, timeout, and range-request support
- Profile-based config system (`~/.earthforge/config.toml`)
- Structured output contract: all commands return Pydantic models, rendered via `--output json|table|csv|quiet`
- Cloud storage abstraction via obstore (S3, GCS, Azure Blob, local filesystem)
- CI: ruff lint, mypy strict, pytest (conda matrix 3.11/3.12), hatch build

### Fixed

- GeoParquet detection only matched `.geoparquet` extension — now reads Parquet footer for `\x03geo` key
- COG validation used deprecated `rasterio.DatasetReader.is_tiled` — now reads `profile.get("tiled", False)`
- COG conversion now uses `PREDICTOR=2` for DEFLATE/LZW/LZMA (30-40% better compression)
- COG overview resampling default changed from `nearest` to `average` (reduces aliasing artifacts)

---

## Version Policy

EarthForge follows [Semantic Versioning](https://semver.org/):

- **0.x.y** — pre-1.0, public API may change between minor versions
- **1.0.0** — stable public API, Rust extension wheels for all platforms, PyPI release
- Minor versions add commands or library functions without breaking existing interfaces
- Patch versions fix bugs without changing public interfaces
