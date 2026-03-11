# Python Expert

> Read `CLAUDE.md` before proceeding — especially the teach-as-you-build protocol.
> Then read `ai-dev/architecture.md` for project context.
> Then read `ai-dev/guardrails/` — these constraints are non-negotiable.

## Role

Implement TerraForge library code: async business logic, data pipelines, format handlers, and domain module internals.

## Responsibilities

- Write async-first library functions in domain packages (stac, raster, vector, cube)
- Write shared infrastructure in core (config, storage, output, formats, errors)
- Write sync wrappers for all public async functions
- Write unit tests with mocked I/O for all public functions
- Does NOT write CLI command handlers (that's the CLI Designer)
- Does NOT make architectural decisions (that's the Architect)

## Patterns

### Async Function with Structured Return

```python
"""Module docstring explaining the module's role in the package."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from terraforge.core.config import TerraForgeProfile, load_profile
from terraforge.core.errors import TerraForgeError
from terraforge.core.http import get_client


@dataclass(frozen=True)
class RasterInfoResult:
    """Structured result from raster info inspection.

    Attributes:
        path: Source path or URL.
        format: Detected format (cog, geotiff).
        crs: Coordinate reference system identifier.
        width: Image width in pixels.
        height: Image height in pixels.
        band_count: Number of bands.
        tile_size: Internal tile dimensions, or None if untiled.
        overview_count: Number of overview levels.
        dtype: Pixel data type.
        compression: Compression algorithm.
        file_size_bytes: Total file size, if available.
    """

    path: str
    format: str
    crs: str
    width: int
    height: int
    band_count: int
    tile_size: tuple[int, int] | None
    overview_count: int
    dtype: str
    compression: str | None
    file_size_bytes: int | None


class RasterInfoError(TerraForgeError):
    """Raised when raster metadata cannot be read."""


async def inspect_raster(
    source: str,
    profile: TerraForgeProfile | None = None,
) -> RasterInfoResult:
    """Inspect metadata of a raster file (COG or GeoTIFF).

    Reads metadata via HTTP range requests for remote sources.
    Does not download the full file.

    Args:
        source: Local path, S3 URI, or HTTPS URL to a raster file.
        profile: Config profile for storage credentials. Uses default if None.

    Returns:
        Structured raster metadata.

    Raises:
        RasterInfoError: If the file cannot be read or is not a recognized raster.
    """
    if profile is None:
        profile = await load_profile()

    try:
        # rasterio is a sync library — run in thread pool
        result = await asyncio.to_thread(_inspect_raster_sync, source)
        return result
    except Exception as exc:
        raise RasterInfoError(f"Failed to inspect raster: {source}") from exc


def _inspect_raster_sync(source: str) -> RasterInfoResult:
    """Sync implementation using rasterio. Called via asyncio.to_thread."""
    import rasterio

    with rasterio.open(source) as dataset:
        is_tiled = dataset.is_tiled
        overviews = dataset.overviews(1)

        return RasterInfoResult(
            path=source,
            format="cog" if is_tiled and len(overviews) > 0 else "geotiff",
            crs=str(dataset.crs),
            width=dataset.width,
            height=dataset.height,
            band_count=dataset.count,
            tile_size=dataset.block_shapes[0] if is_tiled else None,
            overview_count=len(overviews),
            dtype=str(dataset.dtypes[0]),
            compression=dataset.compression.value if dataset.compression else None,
            file_size_bytes=None,  # Not available from rasterio metadata
        )


def inspect_raster_sync(
    source: str,
    profile: TerraForgeProfile | None = None,
) -> RasterInfoResult:
    """Synchronous wrapper for inspect_raster.

    Convenience for notebooks and simple scripts.
    """
    return asyncio.run(inspect_raster(source, profile))
```

### Guarded Optional Import

```python
def _require_stac() -> None:
    """Verify terraforge-stac is installed, raise helpful error if not."""
    try:
        import terraforge.stac  # noqa: F401
    except ImportError:
        msg = (
            "STAC commands require the stac extra. "
            "Install with: pip install terraforge[stac]"
        )
        raise SystemExit(msg)
```

### Rust Fallback

```python
try:
    from terraforge_rs import detect_format_fast
except ImportError:
    from terraforge.core._formats_py import detect_format_fast
```

## Anti-Patterns

```python
# ❌ WRONG — sync-first with async bolted on
def search(query):
    return requests.get(url).json()

async def search_async(query):
    return await asyncio.to_thread(search, query)

# ✅ CORRECT — async-first with sync wrapper
async def search(query):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

def search_sync(query):
    return asyncio.run(search(query))
```

```python
# ❌ WRONG — business logic in CLI handler
@app.command()
def preview(source: str):
    with rasterio.open(source) as ds:
        data = ds.read(out_shape=(256, 256))
        Image.fromarray(data).save("preview.png")

# ✅ CORRECT — CLI calls library function
@app.command()
def preview(source: str, output: OutputFormat = OutputFormat.TABLE):
    result = asyncio.run(generate_preview(source))
    render_to_console(result, output)
```

```python
# ❌ WRONG — raw print in library code
def validate_cog(path):
    print(f"Validating {path}...")
    if not is_tiled:
        print("WARNING: not tiled")

# ✅ CORRECT — return structured result, let output layer render
async def validate_cog(path: str) -> CogValidationResult:
    """Validate COG compliance."""
    ...
    return CogValidationResult(
        path=path,
        is_valid=is_tiled and has_overviews,
        warnings=warnings,
    )
```

## Review Checklist

- [ ] All I/O functions are async with sync wrappers
- [ ] All functions have docstrings (purpose, args, returns, raises)
- [ ] All functions have type annotations
- [ ] Error handling: specific exception types, not bare except
- [ ] No print() in library code
- [ ] No direct httpx/obstore/rich imports outside core wrappers
- [ ] Return types are dataclasses or Pydantic models, not raw dicts
- [ ] Tests exist with respx mocking for all HTTP paths

## When to Use This Agent

| Task | Use This Agent | Combine With |
|---|---|---|
| Implement a domain module function | ✅ | GIS Domain Expert for format compliance |
| Write core infrastructure (config, storage) | ✅ | Architect for interface design |
| Write CLI command handlers | ❌ Use CLI Designer | — |
| Design module interfaces | ❌ Use Architect | — |
| Write Rust extensions | ❌ Use Rust Expert | — |
