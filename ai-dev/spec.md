# EarthForge Specification

> Read `CLAUDE.md` and `ai-dev/architecture.md` before this document.

## Product Definition

EarthForge is a library-first, CLI-first toolkit for working with cloud-native geospatial data. It provides composable, scriptable, pipeline-friendly commands for STAC discovery, COG operations, GeoParquet queries, Zarr datacube access, and format conversion.

EarthForge is NOT a platform, not a web application, not a GIS desktop tool. It is a developer toolkit that integrates with existing workflows.

## Target Users

1. **Cloud-native geospatial developers** — Building pipelines that process STAC collections, COGs, and GeoParquet at scale
2. **GIS practitioners transitioning to cloud** — Converting Shapefiles to GeoParquet, validating COGs, exploring STAC catalogs
3. **Data engineers** — Automating geospatial ETL with declarative pipelines

## Milestone 0 Acceptance Criteria (Foundation)

### Engineering Credibility
- [ ] README leads with the problem statement, not the solution
- [ ] README explicitly states what EarthForge is NOT
- [ ] ARCHITECTURE.md exists at repo root with system design and dependency graph
- [ ] CONTRIBUTING.md states specific engineering standards (async-first, mypy strict, no print, commit format)
- [ ] Git history shows incremental construction: docs → core interfaces → first working command
- [ ] No empty directories, skeleton files, or TODO-only stubs in the repo
- [ ] Decision records DL-001 through DL-006 exist and are linked from README and ARCHITECTURE.md
- [ ] shields.io badges on README: license, Python version, CI status, PyPI version

### Functional
- [ ] Monorepo builds and installs: `pip install -e ".[all,dev]"` succeeds
- [ ] `earthforge --version` prints version
- [ ] `earthforge --help` shows all command groups (config, stac, raster, vector, cube, pipeline)
- [ ] `earthforge info <local-cog.tif>` returns structured COG metadata (dimensions, CRS, bands, tile size, overview count)
- [ ] `earthforge info <local.parquet>` returns structured GeoParquet metadata (schema, CRS, feature count, bbox)
- [ ] `earthforge info` auto-detects format without user specifying it
- [ ] `--output json` on all info commands produces valid JSON matching Pydantic model schema
- [ ] `--output table` produces human-readable Rich table
- [ ] CI passes: ruff lint, mypy strict, pytest (with mocked I/O), hatch build
- [ ] CLAUDE.md, architecture.md, guardrails, and >=3 decision records exist and are referenced

### Real-World Validation
- [ ] `VR-M0-format-detection.md` exists with test results against all format types in `test-data-plan.md`
- [ ] `VR-M0-raster-info.md` exists with test results against Sentinel-2 COGs and Copernicus DEM COGs
- [ ] `VR-M0-vector-info.md` exists with test results against Overture Maps GeoParquet partitions
- [ ] Format detection correctly distinguishes COG from plain GeoTIFF, GeoParquet from plain Parquet
- [ ] Performance baselines recorded: format detection <100ms local, raster info <3s remote

## Milestone 1 Acceptance Criteria (STAC + Raster)

### Functional
- [ ] `earthforge config init` creates `~/.earthforge/config.toml` with default profile
- [ ] `earthforge stac search sentinel-2-l2a --bbox -85,37,-84,38` returns items from Element84 Earth Search
- [ ] `earthforge stac search` works against Planetary Computer with `--profile planetary`
- [ ] `earthforge stac info <item-url>` returns item metadata
- [ ] `earthforge raster info <remote-cog-url>` reads metadata via HTTP range requests (no full download)
- [ ] `earthforge raster preview <remote-cog-url>` generates a PNG quicklook from overview level
- [ ] `earthforge raster validate <file>` checks COG compliance (tiling, overviews, IFD order)
- [ ] All commands support `--output json` for pipeline integration

### Real-World Validation
- [ ] `VR-M1-stac-search.md` — searches against Earth Search and Planetary Computer with results recorded
- [ ] `VR-M1-raster-preview.md` — preview generated from real Sentinel-2 COGs, bytes transferred measured
- [ ] `VR-M1-raster-validate.md` — validation run on real COGs (pass) and non-COG GeoTIFFs (expected fail)
- [ ] STAC search for Kentucky bbox returns expected collections, empty-result searches handled gracefully
- [ ] Performance baselines recorded per `test-data-plan.md` targets

## Milestone 2 Acceptance Criteria (Vector + Conversion)

### Functional
- [ ] `earthforge vector info <file.parquet>` returns schema, CRS, feature count, bbox
- [ ] `earthforge vector query <file.parquet> --bbox -85,37,-84,38` returns matching features using predicate pushdown
- [ ] `earthforge vector convert buildings.shp --to geoparquet` produces valid GeoParquet with spatial index
- [ ] `earthforge raster convert image.tif --to cog` produces valid COG with sensible defaults
- [ ] Rust extension builds and accelerates GeoParquet I/O (with fallback to pure Python)

### Real-World Validation
- [ ] `VR-M2-vector-query.md` — bbox query against Overture Maps buildings with pushdown verified
- [ ] `VR-M2-vector-convert.md` — Shapefile → GeoParquet conversion, output validated by `gpq validate`
- [ ] `VR-M2-raster-convert.md` — GeoTIFF → COG conversion, output validated by `rio cogeo validate`
- [ ] Predicate pushdown confirmed: data transferred significantly less than full file size for bbox queries

## Milestone 3 Acceptance Criteria (Pipeline + Cube)

### Functional
- [ ] `earthforge pipeline validate pipeline.yaml` validates against JSON Schema
- [ ] `earthforge pipeline run pipeline.yaml` executes a STAC→process→export workflow
- [ ] `for_each_item` processes STAC items concurrently with configurable parallelism
- [ ] `earthforge cube info climate.zarr` returns dimensions, variables, chunks
- [ ] `earthforge cube slice climate.zarr --time 2025-06 --bbox -85,37,-84,38` extracts a slice without downloading the full dataset
- [ ] `earthforge stac fetch <item-url>` downloads assets in parallel with resume support

### Real-World Validation
- [ ] `VR-M3-pipeline-run.md` — NDVI pipeline from `test-data-plan.md` executed end-to-end, output COGs validated
- [ ] `VR-M3-cube-info.md` — ERA5 Zarr store inspected via Planetary Computer, lazy loading confirmed
- [ ] `VR-M3-stac-fetch.md` — assets downloaded from Earth Search, file integrity verified
- [ ] Pipeline NDVI outputs pass `rio cogeo validate`

## Milestone 4 Acceptance Criteria (Community + Polish)

- [ ] `earthforge explore` launches interactive TUI for STAC browsing and dataset inspection
- [ ] `earthforge bench vector-query` produces benchmark comparison (GeoParquet vs Shapefile)
- [ ] `earthforge completions bash|zsh|fish` generates shell completions
- [ ] Documentation site (mkdocs-material) deployed with tutorials, CLI reference, and architecture guide
- [ ] v0.1.0 published to PyPI
- [ ] README includes shields.io badges: license, Python version, PyPI version, CI status

## Non-Functional Requirements

- **Performance**: COG preview from remote URL completes in <5 seconds for a 10GB file on a reasonable connection
- **Install size**: `pip install earthforge[stac]` installs <50MB of dependencies (excluding GDAL)
- **Compatibility**: Works on Linux, macOS, Windows. Rust extension provides pre-built wheels for all three.
- **Accessibility**: CLI output respects `NO_COLOR` environment variable and `--no-color` flag
