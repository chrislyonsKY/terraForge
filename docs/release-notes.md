# Release Notes

## v1.0.0 — 2026-03-17

EarthForge reaches 1.0.0 with full feature completeness, Rust acceleration scaffolding, comprehensive documentation, CI/CD hardening, and 429 passing tests across Python 3.11/3.12/3.13.

### Added — M5 (Feature Completeness)

**Accessibility (WCAG 2.1 AA):**

- `FORCE_COLOR` env var support alongside `NO_COLOR`
- `StatusMarker` enum — text markers (`[PASS]`/`[FAIL]`/`[WARN]`) alongside color for all status output
- `--high-contrast` global CLI flag for 4.5:1 contrast ratio styling
- `earthforge.core.palettes` — colorblind-safe palette constants (viridis, cividis, BrBG, Set2, Paired)
- TUI accessibility: `name` attributes on all containers, focus-to-items-table after collection selection, 3:1 focus indicator contrast

**Validation commands:**

- `earthforge stac validate` — STAC item/collection validation against spec via pystac
- `earthforge vector validate` — GeoParquet schema compliance (geo metadata, CRS, encoding)
- `earthforge cube validate` — Zarr/NetCDF structure compliance (chunks, CF-convention, CRS)

**Raster extensions:**

- `earthforge raster stats` — global/zonal statistics (min, max, mean, std, median, histogram)
- `earthforge raster calc` — band math with safe expression evaluator
- `earthforge raster tile` — XYZ/TMS static tile generation with inline tile math

**Vector extensions:**

- `earthforge vector clip` — spatial clipping by bbox or WKT geometry
- `earthforge vector tile` — GeoParquet to PMTiles (tippecanoe or built-in fallback)

**Cube extensions:**

- `earthforge cube convert` — NetCDF to/from Zarr with rechunking
- `earthforge cube stats` — aggregate statistics along dimensions (mean, min, max, std, sum)

**STAC extensions:**

- `earthforge stac publish` — push items to writable STAC APIs via Transaction Extension

**Core infrastructure:**

- `earthforge.core.expression` — safe AST-walking expression evaluator with comparisons and safe functions (clip, where, abs, sqrt, log)
- Pipeline `steps.py` refactored to import from `core.expression`
- Error types added: `StacValidationError`, `StacPublishError`, `VectorValidationError`

### Added — M6 (Rust Acceleration)

- `packages/rs/` — PyO3/maturin Rust extension package
- `detect_format_batch` — Rayon-parallel magic byte sniffing across many files
- `parallel_range_read` — Tokio concurrent HTTP range reads
- `read_geoparquet_fast` — Arrow FFI stub for zero-copy GeoParquet reading
- Fallback tests ensure pure-Python path works when Rust extension is not installed

### Added — M7 (Docs & Developer Experience)

- `SECURITY` — security policy with vulnerability reporting, design principles, contributor checklist
- `examples/outputs/README.md` — output gallery standards (WCAG, cartographic elements, data citation)
- `examples/outputs/` — 14 real-world output images with `.txt` sidecar files
- 30+ example scripts across 4 continents (US, Europe, South America, Asia-Pacific)
- ArcGIS Pro Python Toolbox expanded from 5 to 14 tools
- GitHub Pages site updated: Examples tab replaces Tutorials, CLI reference expanded, API reference expanded

### Added — M8 (CI/CD & Beta)

- Python 3.13 added to CI test matrix
- `--cov-fail-under=80` coverage threshold
- PyPI trusted publishing via OIDC (no stored API tokens)
- `.pre-commit-config.yaml` — ruff lint + format, trailing whitespace, no-commit-to-branch
- `cliff.toml` — git-cliff changelog generation from conventional commits
- Cube and pipeline packages added to CI test/typecheck/build paths

### Changed — M9 (Hardening)

- All packages bumped to 1.0.0
- Classifier changed to `Development Status :: 5 - Production/Stable`
- `pyproject.toml` testpaths includes all 7 packages
- `vegetation_change_gif.py` updated to use colorblind-safe BrBG palette

---

## v0.1.1 — 2026-03-12

### Fixed

- PyPI package URLs corrected in all sub-package `pyproject.toml` files
- ArcGIS Pro toolbox `SearchResultItem` properties attribute fix

---

## v0.1.0 — 2026-03-10

### Added — M4 (Polish)

- `earthforge explore` — interactive full-screen STAC browser (Textual TUI)
- `earthforge completions bash|zsh|fish` — shell completion script generation
- `earthforge bench vector-query` — GeoParquet predicate pushdown vs full scan benchmark
- `earthforge bench raster-info` — COG header range-request timing benchmark

### Added — M3 (Pipeline + Cube)

- `earthforge pipeline validate/run/list/init` — declarative YAML pipeline executor
- Pipeline step registry: `stac.fetch`, `raster.calc`, `raster.convert`, `vector.convert`
- Safe band math AST evaluator (no `eval`/`exec`)
- `earthforge cube info` — lazy Zarr/NetCDF metadata (dimensions, variables, spatial bbox, time range)
- `earthforge cube slice` — spatiotemporal subset extraction without full download
- `earthforge stac fetch` — parallel asset download with resume support

### Added — M2 (Vector + Conversion)

- `earthforge vector info` — GeoParquet schema, CRS, feature count, bbox, geometry types
- `earthforge vector convert` — Shapefile/GeoJSON/GPKG to GeoParquet 1.1.0 with bbox covering column
- `earthforge vector query` — spatial bbox query with pyarrow predicate pushdown
- `earthforge raster convert` — GeoTIFF to COG via GDAL COG driver with auto overviews

### Added — M1 (STAC + Raster)

- `earthforge stac search` — search any STAC API with bbox, datetime, and collection filters
- `earthforge stac info` — inspect STAC items and collections from a URL
- `earthforge raster info` — COG metadata via HTTP range requests (no full download)
- `earthforge raster preview` — PNG quicklook from overview level
- `earthforge raster validate` — COG compliance check (tiling, overviews, IFD order)
- `earthforge config init/set/get` — profile management

### Added — M0 (Foundation)

- Format detection chain: magic bytes, extension, content inspection
- Async HTTP client with retry, timeout, and range-request support
- Profile-based config system (`~/.earthforge/config.toml`)
- Structured output contract: all commands return Pydantic models, rendered via `--output json|table|csv|quiet`
- Cloud storage abstraction via obstore (S3, GCS, Azure Blob, local filesystem)
- CI: ruff lint, mypy strict, pytest (conda matrix), hatch build

### Fixed

- GeoParquet detection reads Parquet footer for `geo` key (not just `.geoparquet` extension)
- COG validation uses `profile.get("tiled", False)` instead of deprecated `is_tiled`
- COG conversion uses `PREDICTOR=2` for DEFLATE/LZW/LZMA (30-40% better compression)
- COG overview resampling default changed from `nearest` to `average`

---

## Version Policy

EarthForge follows [Semantic Versioning](https://semver.org/):

- **1.x.y** — stable public API; minor versions add features, patch versions fix bugs
- Backwards-incompatible changes require a major version bump with deprecation warnings in the prior minor release
- Rust extension (`earthforge-rs`) is always optional; pure-Python fallbacks are maintained
