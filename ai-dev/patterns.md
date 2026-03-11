# EarthForge Code Patterns

## Established Patterns

### Async-first with sync wrapper
Every public I/O function is async. A `_sync` suffixed wrapper calls `asyncio.run()` for convenience. The async function is the primary API.

### Structured return types
Functions return frozen dataclasses or Pydantic models, never raw dicts. This enables type-safe output formatting and JSON schema generation.

### Guarded optional imports
The CLI uses try/except import to gracefully handle missing optional packages, providing install instructions on failure.

### Rust fallback
Rust-accelerated functions always have a pure-Python fallback. Guard with try/except import.

### Config-driven, not flag-driven
STAC API URLs, storage credentials, and default settings come from profiles in `~/.earthforge/config.toml`. CLI flags override profiles, not replace them.

## Anti-Patterns (Do NOT Do These)

### Direct third-party imports in domain code
```python
# ❌ WRONG
import httpx
response = await httpx.get(url)

# ✅ CORRECT
from earthforge.core.http import get_client
client = await get_client(profile)
response = await client.get(url)
```

### Business logic in CLI handlers
```python
# ❌ WRONG — rasterio logic in the command handler
@raster_app.command()
def info(source: str):
    with rasterio.open(source) as ds:
        typer.echo(f"Size: {ds.width}x{ds.height}")

# ✅ CORRECT — CLI calls library, formats result
@raster_app.command()
def info(source: str, output: OutputFormat = OutputFormat.TABLE):
    result = asyncio.run(inspect_raster(source))
    render_to_console(result, output)
```

### Full dataset reads for subset operations
```python
# ❌ WRONG — reads all data then filters
gdf = gpd.read_parquet("huge.parquet")
subset = gdf.cx[-85:-84, 37:38]

# ✅ CORRECT — predicate pushdown at storage layer
gdf = gpd.read_parquet("huge.parquet", bbox=(-85, 37, -84, 38))
```

### Unstructured error messages
```python
# ❌ WRONG
raise Exception("something went wrong")

# ✅ CORRECT
raise CogValidationError(
    f"COG validation failed for {path}: missing overviews. "
    f"Convert with: earthforge raster convert {path} --to cog"
)
```
