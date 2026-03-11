# EarthForge Architecture

> Read `CLAUDE.md` first. This document provides the detailed system design.

---

## System Overview

EarthForge is a library-first, CLI-first toolkit for working with cloud-native geospatial data. The library layer provides async Python APIs for STAC discovery, COG operations, GeoParquet queries, and Zarr datacube access. The CLI layer is a thin Typer application that dispatches to library functions and formats output.

The design prioritizes composability over completeness. EarthForge is not a platform — it is a set of focused tools that integrate with existing workflows via structured output, stdin/stdout piping, and Python imports.

---

## Package Dependency Graph

```
earthforge (meta-package)
├── earthforge-core (required)
│   ├── httpx         → async HTTP client
│   ├── obstore       → S3/GCS/Azure/local storage
│   ├── pydantic      → config, validation, output models
│   ├── rich          → terminal formatting
│   └── orjson        → fast JSON serialization
├── earthforge-cli (optional: cli)
│   ├── earthforge-core
│   └── typer         → CLI framework
├── earthforge-stac (optional: stac)
│   ├── earthforge-core
│   ├── pystac-client → STAC API search
│   └── pystac        → STAC object model
├── earthforge-raster (optional: raster)
│   ├── earthforge-core
│   ├── rasterio      → COG I/O via GDAL
│   ├── numpy         → array operations
│   └── Pillow        → preview PNG generation
├── earthforge-vector (optional: vector)
│   ├── earthforge-core
│   ├── geopandas     → GeoParquet ergonomic API
│   └── pyarrow       → Arrow/Parquet engine
├── earthforge-cube (optional: cube)
│   ├── earthforge-core
│   ├── xarray        → labeled multidimensional arrays
│   ├── zarr          → Zarr format I/O
│   └── h5netcdf      → NetCDF support
└── earthforge-rs (optional, Rust acceleration)
    └── PyO3/maturin  → Python extension from Rust
```

The dependency arrow is strictly one-directional: domain packages → core. Core never imports from domain packages. The CLI imports from domain packages via guarded optional imports.

---

## Module Interface Contracts

### earthforge.core.config

```python
@dataclass
class EarthForgeProfile:
    name: str
    stac_api: str | None
    storage_backend: str          # "s3" | "gcs" | "azure" | "local"
    storage_options: dict[str, str]  # backend-specific credentials/config

async def load_profile(name: str = "default") -> EarthForgeProfile
async def init_config() -> Path  # creates ~/.earthforge/config.toml
```

Config file format (TOML, parsed with stdlib tomllib):
```toml
[profiles.default]
stac_api = "https://earth-search.aws.element84.com/v1"
storage = "s3"

[profiles.default.storage_options]
region = "us-west-2"

[profiles.planetary]
stac_api = "https://planetarycomputer.microsoft.com/api/stac/v1"
storage = "azure"

[profiles.planetary.storage_options]
account_name = "pcstacitems"
sas_token_endpoint = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
```

### earthforge.core.storage

```python
class StorageClient:
    """Unified cloud storage abstraction wrapping obstore."""

    @classmethod
    async def from_profile(cls, profile: EarthForgeProfile) -> StorageClient

    async def get(self, path: str) -> bytes
    async def get_range(self, path: str, start: int, end: int) -> bytes
    async def put(self, path: str, data: bytes) -> None
    async def list(self, prefix: str) -> AsyncIterator[str]
    async def head(self, path: str) -> ObjectMeta
```

### earthforge.core.output

```python
class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"
    CSV = "csv"
    QUIET = "quiet"

def render(data: BaseModel | list[BaseModel], fmt: OutputFormat) -> str
def render_to_console(data: BaseModel | list[BaseModel], fmt: OutputFormat) -> None
```

All CLI commands produce Pydantic models. The output module serializes them. This is the structured output contract — `--output json` always produces valid JSON matching the model schema.

### earthforge.core.formats

```python
class FormatType(StrEnum):
    COG = "cog"
    GEOTIFF = "geotiff"
    GEOPARQUET = "geoparquet"
    PARQUET = "parquet"
    FLATGEOBUF = "flatgeobuf"
    ZARR = "zarr"
    NETCDF = "netcdf"
    COPC = "copc"
    STAC_ITEM = "stac_item"
    STAC_COLLECTION = "stac_collection"
    STAC_CATALOG = "stac_catalog"
    GEOJSON = "geojson"
    UNKNOWN = "unknown"

async def detect(source: str) -> FormatType
```

Detection chain: magic bytes (first 512 bytes via range read) → file extension → content inspection (format-specific metadata checks). Domain packages register their detectors at import time via a registry pattern.

### earthforge.core.errors

```python
class EarthForgeError(Exception):
    """Base exception for all EarthForge errors."""
    exit_code: int = 1

class ConfigError(EarthForgeError): ...
class StorageError(EarthForgeError): ...
class FormatDetectionError(EarthForgeError): ...

# Domain packages extend:
# class StacSearchError(EarthForgeError): ...
# class CogValidationError(EarthForgeError): ...
# class GeoParquetSchemaError(EarthForgeError): ...
```

---

## CLI Command Architecture

### Command Tree

```
earthforge
├── config
│   ├── init              # Create ~/.earthforge/config.toml
│   ├── set               # Set a config value
│   ├── get               # Get a config value
│   └── profile           # Manage named profiles
├── stac
│   ├── search            # Search a STAC API
│   ├── info              # Inspect item/collection/catalog
│   ├── validate          # Validate STAC JSON against spec
│   ├── fetch             # Download assets from a STAC item
│   └── publish           # Push items to a writable STAC API
├── raster
│   ├── info              # COG metadata, block structure, overviews
│   ├── validate          # COG compliance check
│   ├── convert           # GeoTIFF → COG, reproject, rescale
│   ├── preview           # Quicklook PNG via HTTP range requests
│   ├── tile              # Generate XYZ/TMS web tiles from COG
│   ├── calc              # Band math / spectral indices
│   └── stats             # Zonal/global statistics
├── vector
│   ├── info              # Schema, CRS, feature count, bbox
│   ├── validate          # GeoParquet schema compliance
│   ├── convert           # Format conversion (shp/geojson → geoparquet)
│   ├── query             # Spatial/attribute query with bbox/SQL
│   ├── tile              # GeoParquet → PMTiles/MVT
│   └── clip              # Clip to geometry/bbox
├── cube
│   ├── info              # Dimensions, variables, chunks, metadata
│   ├── validate          # Zarr/NetCDF structure compliance
│   ├── convert           # NetCDF ↔ Zarr, rechunk
│   ├── slice             # Spatiotemporal extraction
│   └── stats             # Aggregate statistics along dimensions
├── pipeline
│   ├── run               # Execute pipeline YAML
│   ├── validate          # Validate pipeline YAML schema
│   ├── list              # List available pipeline steps
│   └── init              # Generate starter pipeline template
└── completions           # Shell completion scripts (bash/zsh/fish)
```

### Global Flags

```
--profile <name>             Named config profile
--output / -o <format>       json | table | csv | quiet
--verbose / -v               Increase verbosity (stackable: -vvv)
--no-color                   Disable colored output
--progress / --no-progress   Toggle progress bars
```

### CLI Pattern

Every command handler follows the same pattern:

```python
@raster_app.command()
def info(
    source: str = typer.Argument(help="Path or URL to a raster file"),
    output: OutputFormat = typer.Option(OutputFormat.TABLE, "--output", "-o"),
    profile: str = typer.Option("default", "--profile"),
) -> None:
    """Inspect metadata of a raster file (COG, GeoTIFF)."""
    result = asyncio.run(_info(source, profile))
    render_to_console(result, output)

async def _info(source: str, profile: str) -> RasterInfoResult:
    cfg = await load_profile(profile)
    # ... call library function, return structured result
```

The handler: parses arguments → calls async library function via asyncio.run() → renders output. No business logic.

---

## Async I/O Architecture

### Why Async-First

Cloud-native geospatial operations are I/O-bound: STAC API calls, COG range requests, S3 object reads. Async enables concurrent operations without threads:

- Searching 5 STAC APIs in parallel
- Issuing 50 range reads for COG tile access
- Downloading 20 STAC assets concurrently

### Pattern

```python
# Library function — async is the primary API
async def search_catalog(
    api_url: str,
    collection: str,
    bbox: BBox | None = None,
    datetime_range: str | None = None,
) -> list[StacItem]:
    ...

# Sync wrapper — convenience for notebooks and scripts
def search_catalog_sync(...) -> list[StacItem]:
    return asyncio.run(search_catalog(...))
```

### HTTP Client

All HTTP goes through a shared `httpx.AsyncClient` managed by `earthforge.core.http`:

```python
async def get_client(profile: EarthForgeProfile) -> httpx.AsyncClient:
    """Return a configured async HTTP client with auth, timeouts, retries."""
```

This ensures consistent timeout settings, retry policies, and auth header injection.

---

## Rust Extension Boundary (packages/rs)

### What Goes in Rust

1. Format detection — magic byte sniffing across many files
2. Parallel HTTP range reads — tokio async runtime + zero-copy assembly
3. GeoParquet I/O — geoarrow-rs for large dataset acceleration

### What Stays in Python

Everything else. STAC search logic, config management, output formatting, CLI dispatch, pipeline execution.

### Fallback Pattern

```python
try:
    from earthforge_rs import detect_format_fast
except ImportError:
    from earthforge.core._formats_py import detect_format_fast
```

The Rust extension is always optional. Pure Python implementations exist for all Rust-accelerated functions.

### Build System

`packages/rs/pyproject.toml` uses maturin:
```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"
```

NOT hatchling. This was incorrect in the original scaffold.

---

## Pipeline Schema (Deferred — Milestone 3)

Pipeline YAML must include:
- `version: "1"` — schema version for forward compatibility
- `name:` — pipeline identifier
- `source:` — data source (STAC search, file list, or glob)
- `steps:` — ordered list of operations, dotted names matching library structure
- `sink:` — output target (local, S3, STAC publish)

The `for_each_item` iterator enables parallel processing of STAC search results.

Pipeline steps are registered via Python entry points, enabling plugins to add custom steps.

Expression evaluation (band math) uses a safe parser, NEVER `eval()` or `exec()`.

---

## Testing Strategy

| Layer | Tool | What It Catches | Coverage |
|---|---|---|---|
| Unit tests | pytest + respx | Logic errors, type mismatches, edge cases | ~80% of suite |
| Integration tests | pytest + pytest-recording | API compatibility, auth flows, real data | ~15% of suite |
| Type checking | mypy --strict | Type errors, missing annotations | All source |
| Lint | ruff | Style, imports, print() usage, datetime safety | All source |

Unit tests mock all I/O via `respx` (async HTTP) and obstore local filesystem backend. Integration tests use VCR-recorded responses from real APIs, re-recorded periodically. Tests tagged `@pytest.mark.integration` are excluded from CI by default.
