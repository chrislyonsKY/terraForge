# Architecture

EarthForge's design is documented here, not as an afterthought, but as the foundation the implementation is built on. Every major decision has a decision record in [`ai-dev/decisions/`](https://github.com/chrislyonsKY/earthForge/tree/main/ai-dev/decisions/).

## Design Principles

**Library-first, CLI-second.** All business logic lives in domain packages. The CLI is a thin dispatch layer — it parses arguments, calls library functions, and formats output. Anything you can do from the CLI, you can do from Python.

**Async-first I/O.** Cloud-native geospatial work is I/O-bound. The primary API is `async def`. Sync wrappers exist for notebooks and scripts, but async is the canonical path. See [DL-002](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-002-async-first-io.md).

**Structured output as a contract.** Every CLI command returns a Pydantic model rendered by a central output module. `--output json` always produces valid JSON conforming to a versioned schema — not ad-hoc serialization. See [DL-004](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-004-output-contract.md).

**Format detection, not format flags.** `earthforge info <file>` auto-detects COG, GeoParquet, Zarr, STAC, and more. The detection chain uses magic bytes, file extension fallback, and content inspection (e.g., reading the Parquet footer for the GeoParquet `geo` metadata key).

## Package Dependency Graph

```
earthforge (meta-package)
├── earthforge-core          (always required)
│   ├── httpx                → async HTTP client
│   ├── obstore              → S3/GCS/Azure/local storage abstraction
│   ├── pydantic             → config, validation, output models
│   ├── rich                 → terminal table rendering
│   └── orjson               → fast JSON serialization
├── earthforge-cli           (optional: earthforge[cli])
│   └── typer                → CLI framework
├── earthforge-stac          (optional: earthforge[stac])
│   ├── pystac-client        → STAC API search with pagination
│   └── pystac               → STAC object model
├── earthforge-raster        (optional: earthforge[raster])
│   ├── rasterio             → COG I/O via GDAL
│   ├── numpy                → array operations
│   └── Pillow               → PNG preview generation
├── earthforge-vector        (optional: earthforge[vector])
│   ├── pyarrow              → Arrow/Parquet I/O with predicate pushdown
│   └── GDAL/OGR             → format reading (Shapefile, GeoJSON, GPKG)
└── earthforge-cube          (optional: earthforge[cube])
    ├── xarray               → labeled N-D arrays
    ├── zarr                 → Zarr format I/O
    └── h5netcdf             → NetCDF via HDF5 (optional)
```

Dependencies flow one direction: domain packages → core. Core never imports from domain packages. The CLI imports from domain packages via guarded try/except, producing helpful installation hints when a package is absent.

## Module Structure

Each domain package follows the same internal layout:

```
packages/{domain}/
├── pyproject.toml
└── src/earthforge/{domain}/
    ├── __init__.py      # version, public API re-exports
    ├── errors.py        # domain-specific exception subclasses
    ├── info.py          # read + inspect operations
    ├── validate.py      # compliance checking
    ├── convert.py       # format conversion
    └── ...
```

## Async I/O Pattern

```python
# Primary API — async
async def inspect_raster(source: str) -> RasterInfo:
    async with managed_client(profile) as client:
        ...

# Convenience wrapper — sync
def inspect_raster_sync(source: str) -> RasterInfo:
    return asyncio.run(inspect_raster(source))
```

The CLI uses `asyncio.run()` in the command handler. Notebooks can `await` the async function directly.

## Output Contract

```
CLI command
    │
    ▼
async library function ──► Pydantic model
                                │
                        render_to_console()
                                │
                    ┌───────────┴───────────┐
                  table                   json
                (Rich)                 (orjson)
```

All CLI output goes through `earthforge.core.output`. Commands never call `print()`. This ensures `--output json` always works without extra code per command, and a new output format (e.g., CSV, YAML) requires changes in exactly one place.

## Format Detection Chain

```
detect(source)
    │
    ├── 1. Read first 512 bytes (local: file read; remote: HTTP Range request)
    │
    ├── 2. Match magic bytes
    │       TIFF → candidate: GEOTIFF
    │       PAR1 → candidate: PARQUET
    │       fgb  → candidate: FLATGEOBUF
    │       HDF5 → candidate: NETCDF
    │
    ├── 3. Extension fallback (if no magic match)
    │       .tif → GEOTIFF
    │       .parquet → PARQUET
    │       .geojson → GEOJSON
    │
    └── 4. Content inspectors (registered, called in order)
            GEOTIFF → COG? (check TileWidth tag 0x0142 in header)
            PARQUET → GEOPARQUET? (read last 4KB, find \x03geo key)
            GEOJSON → STAC? (check for stac_version in header bytes)
```

## Decision Records

| # | Decision | Summary |
|---|----------|---------|
| [DL-001](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-001-monorepo.md) | Monorepo with Hatch workspace | Single repo, independent installable packages |
| [DL-002](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-002-async-first-io.md) | Async-first I/O | httpx AsyncClient, asyncio.TaskGroup for parallelism |
| [DL-003](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-003-storage-abstraction.md) | obstore for cloud storage | Rust-backed, not fsspec |
| [DL-004](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-004-output-contract.md) | Pydantic output contract | Structured output, not ad-hoc serialization |
| [DL-005](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-005-rust-boundary.md) | Rust extension boundary | Rust for hot paths; Python for orchestration |
| [DL-006](https://github.com/chrislyonsKY/earthForge/blob/main/ai-dev/decisions/DL-006-engineering-credibility.md) | Engineering credibility | Nothing ships empty; incremental construction |
