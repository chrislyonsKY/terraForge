# CLI Reference

EarthForge is invoked as `earthforge`. All commands support these global flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `table` | Output format: `table`, `json`, `csv`, `quiet` |
| `--profile` | `default` | Named config profile from `~/.earthforge/config.toml` |
| `--verbose`, `-v` | off | Increase verbosity (stackable: `-vvv`) |
| `--no-color` | off | Disable colored output |
| `--version`, `-V` | — | Print version and exit |

---

## `earthforge info`

Inspect any geospatial file. Format is auto-detected from magic bytes — no flags required.

```bash
earthforge info <path-or-url>
```

**Examples**

```bash
# Local file
earthforge info buildings.parquet

# Remote COG via HTTP range request (no full download)
earthforge info s3://sentinel-cogs/.../B04.tif

# JSON output for scripting
earthforge info scene.tif --output json
```

---

## `earthforge config`

Manage profiles in `~/.earthforge/config.toml`.

```bash
earthforge config init              # Create default config
earthforge config set <key> <value> # Set a profile key
earthforge config get <key>         # Print a profile key
```

**Example config**

```toml
[profiles.default]
stac_api = "https://earth-search.aws.element84.com/v1"
storage = "s3"

[profiles.default.storage_options]
region = "us-west-2"

[profiles.planetary]
stac_api = "https://planetarycomputer.microsoft.com/api/stac/v1"
storage = "azure"
```

---

## `earthforge stac`

Search and download from STAC APIs.

### `stac search`

```bash
earthforge stac search <collection> [options]

Options:
  --bbox         west,south,east,north
  --datetime     2024-01-01/2024-12-31  (ISO 8601 interval)
  --max-items    50
  --profile      default
  --output       table | json | csv | quiet
```

```bash
# Sentinel-2 over Kentucky, summer 2025
earthforge stac search sentinel-2-l2a \
  --bbox -85,37,-84,38 \
  --datetime 2025-06/2025-09 \
  --max-items 10

# Output as JSON for piping
earthforge stac search sentinel-2-l2a --bbox -85,37,-84,38 -o json \
  | jq '.items[].assets.B04.href'
```

### `stac info`

```bash
earthforge stac info <item-url>
```

### `stac fetch`

Download assets in parallel with resume support.

```bash
earthforge stac fetch <item-url> \
  --assets red,green,blue,nir \
  --output-dir ./data \
  --parallel 4
```

Re-running the same command skips already-complete files.

---

## `earthforge raster`

COG operations.

### `raster info`

```bash
earthforge raster info <path-or-url>
```

Returns: dimensions, CRS, band count, tile size, overview levels, compression, nodata.

### `raster validate`

```bash
earthforge raster validate <path-or-url>
```

Checks: tiling, overview presence, IFD ordering, compression. Exits `0` on pass, `1` on fail.

### `raster preview`

Generate a PNG quicklook from the overview level. Reads only overview data — not the full file.

```bash
earthforge raster preview <path-or-url> -o preview.png
```

### `raster convert`

Convert a GeoTIFF to a Cloud Optimized GeoTIFF using the GDAL COG driver.

```bash
earthforge raster convert image.tif --to cog

Options:
  --compression   deflate | lzw | zstd | none   (default: deflate)
  --blocksize     256 | 512                      (default: 512)
  --resampling    average | nearest              (default: average)
  --output        output filename                (default: <input>_cog.tif)
```

---

## `earthforge vector`

GeoParquet operations.

### `vector info`

```bash
earthforge vector info <file.parquet>
```

Returns: schema, CRS, feature count, geometry types, spatial bbox.

### `vector convert`

Convert Shapefile, GeoJSON, or GPKG to GeoParquet 1.1.0.

```bash
earthforge vector convert buildings.shp --to geoparquet

Options:
  --to        geoparquet                     (only supported target currently)
  --output    output filename                (default: <input>.parquet)
```

Output includes WKB geometry encoding, PROJJSON CRS metadata, and a bbox covering column
for predicate pushdown.

### `vector query`

Spatial bbox query with pyarrow predicate pushdown.

```bash
earthforge vector query buildings.parquet \
  --bbox -85,37,-84,38 \
  --columns id,height,geometry \
  --limit 1000 \
  --output json
```

---

## `earthforge cube`

Zarr and NetCDF datacube operations.

### `cube info`

```bash
earthforge cube info climate.zarr
```

Returns: dimensions, variables, chunks, spatial bbox, time range, CF attributes. Uses consolidated `.zmetadata` — no full download.

### `cube slice`

Extract a spatiotemporal subset without downloading the full dataset.

```bash
earthforge cube slice era5.zarr \
  --time 2024-06/2024-08 \
  --bbox -85,37,-84,38 \
  --variables t2m,u10,v10 \
  --output subset.zarr
```

---

## `earthforge pipeline`

Declarative YAML pipelines.

```bash
earthforge pipeline validate pipeline.yaml   # Validate against JSON Schema
earthforge pipeline run pipeline.yaml        # Execute the pipeline
earthforge pipeline list                     # List registered step types
earthforge pipeline init                     # Generate a starter NDVI template
```

**Minimal pipeline YAML**

```yaml
name: ndvi-lexington
version: "1.0"

steps:
  - id: search
    type: stac.fetch
    collection: sentinel-2-l2a
    bbox: [-84.6, 37.9, -84.4, 38.1]
    assets: [B04, B08]

  - id: ndvi
    type: raster.calc
    inputs: [search]
    expression: "(B08 - B04) / (B08 + B04)"
    output: ndvi.tif
```

---

## `earthforge explore`

Interactive full-screen STAC browser (requires `textual`).

```bash
earthforge explore [options]

Options:
  --api         STAC API root URL   (default: Earth Search)
  --collection  Pre-select collection on startup
  --bbox        west,south,east,north  (applied to item searches)
```

```bash
# Browse Element84 Earth Search
earthforge explore

# Open directly on a collection, filtered to Kentucky
earthforge explore \
  --api https://earth-search.aws.element84.com/v1 \
  --collection sentinel-2-l2a \
  --bbox -85,37,-84,38
```

**Keyboard shortcuts**

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate within a panel |
| `Enter` | Select collection or item |
| `Tab` / `Shift+Tab` | Cycle focus between panels |
| `r` | Refresh collection list |
| `q` | Quit |

---

## `earthforge bench`

Performance benchmarks.

```bash
earthforge bench vector-query   # GeoParquet predicate pushdown vs full scan
earthforge bench raster-info    # COG header read timing via HTTP range request
```

---

## `earthforge completions`

Generate shell completion scripts.

```bash
earthforge completions bash >> ~/.bashrc
earthforge completions zsh  >> ~/.zshrc
earthforge completions fish > ~/.config/fish/completions/earthforge.fish
```
