# CLI Reference

EarthForge is invoked as `earthforge`. All commands support these global flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `table` | Output format: `table`, `json`, `csv`, `quiet` |
| `--profile` | `default` | Named config profile from `~/.earthforge/config.toml` |
| `--verbose`, `-v` | off | Increase verbosity (stackable: `-vvv`) |
| `--no-color` | off | Disable colored output |
| `--high-contrast` | off | High-contrast mode (WCAG 2.1 AA compliant) |
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

### `stac validate`

Validate STAC items and collections against the STAC specification.

```bash
earthforge stac validate <item-or-collection-url>
```

Checks: required fields, link relations, asset roles, datetime formatting, spatial extent validity. Exits `0` on pass, `1` on fail.

### `stac publish`

Publish items to a writable STAC API (Transaction Extension).

```bash
earthforge stac publish <item.json> --api <stac-api-url>

Options:
  --api           Target STAC API URL (must support Transaction Extension)
  --collection    Target collection ID
  --profile       Named config profile
```

```bash
# Publish a local STAC item
earthforge stac publish item.json \
  --api https://your-stac-api.example.com/ \
  --collection my-collection
```

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

### `raster stats`

Compute raster statistics: min, max, mean, standard deviation, median, and histogram.

```bash
earthforge raster stats <path-or-url>

Options:
  --bands         1,2,3           (default: all bands)
  --percentiles   5,25,50,75,95   (custom percentile list)
  --histogram     256             (number of bins, default: 256)
  --output        table | json    (default: table)
```

```bash
# Full statistics for a DEM
earthforge raster stats elevation.tif

# Histogram with custom bins for band 1 only
earthforge raster stats scene.tif --bands 1 --histogram 128 -o json
```

### `raster calc`

Band math with a safe expression evaluator. No `eval()` — expressions are parsed and validated.

```bash
earthforge raster calc <path-or-url> --expression "<expr>" --output <output.tif>

Options:
  --expression    Band math expression (e.g., "(B08 - B04) / (B08 + B04)")
  --output        Output filename (required)
  --nodata        Nodata value for output (default: NaN)
```

```bash
# NDVI from Sentinel-2
earthforge raster calc scene.tif \
  --expression "(B08 - B04) / (B08 + B04)" \
  --output ndvi.tif

# Simple band ratio
earthforge raster calc scene.tif \
  --expression "B05 / B04" \
  --output ratio.tif
```

### `raster tile`

Generate XYZ/TMS static tile pyramids from a raster file.

```bash
earthforge raster tile <path-or-url> --output-dir <dir>

Options:
  --min-zoom      0          (minimum zoom level)
  --max-zoom      14         (maximum zoom level)
  --tile-size     256        (tile dimensions in pixels)
  --format        png | webp (default: png)
  --output-dir    ./tiles    (output directory)
```

```bash
# Generate web map tiles
earthforge raster tile elevation.tif --output-dir ./tiles --max-zoom 12
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

### `vector validate`

Validate GeoParquet compliance (metadata, geometry encoding, CRS, bbox covering).

```bash
earthforge vector validate <file.parquet>
```

Checks: GeoParquet metadata version, WKB geometry encoding, PROJJSON CRS, bbox covering column, row group statistics. Exits `0` on pass, `1` on fail.

### `vector clip`

Clip features to a bounding box or geometry file.

```bash
earthforge vector clip <file.parquet> --bbox west,south,east,north --output <output.parquet>

Options:
  --bbox          west,south,east,north
  --geometry      Path to clipping geometry (GeoJSON, Parquet)
  --output        Output filename (required)
```

```bash
# Clip buildings to a city extent
earthforge vector clip buildings.parquet \
  --bbox -84.55,38.0,-84.45,38.1 \
  --output lexington_buildings.parquet
```

### `vector tile`

Generate PMTiles from vector data.

```bash
earthforge vector tile <file.parquet> --output <output.pmtiles>

Options:
  --min-zoom      0          (minimum zoom level)
  --max-zoom      14         (maximum zoom level)
  --layer-name    default    (MVT layer name)
  --output        output.pmtiles (required)
```

```bash
# Generate PMTiles for web maps
earthforge vector tile buildings.parquet \
  --output buildings.pmtiles \
  --max-zoom 14
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

### `cube validate`

Validate datacube structure: chunk consistency, dimension ordering, CF attributes, coordinate metadata.

```bash
earthforge cube validate <path.zarr>
```

Checks: Zarr v2/v3 structure, dimension coordinates, chunk alignment, CF convention attributes (`units`, `standard_name`, `calendar`). Exits `0` on pass, `1` on fail.

### `cube convert`

Convert between NetCDF and Zarr formats.

```bash
earthforge cube convert <input> --to zarr|netcdf --output <output>

Options:
  --to            zarr | netcdf  (target format)
  --output        Output path (required)
  --chunks        auto | <dim>=<size>  (rechunk on conversion)
  --compression   zlib | zstd | blosc  (default: zlib)
```

```bash
# NetCDF to Zarr with rechunking
earthforge cube convert climate.nc --to zarr --output climate.zarr --chunks time=24,lat=180,lon=360

# Zarr to NetCDF
earthforge cube convert dataset.zarr --to netcdf --output dataset.nc
```

### `cube stats`

Aggregate statistics along dimensions.

```bash
earthforge cube stats <path.zarr> --variable <var>

Options:
  --variable      Variable name (required)
  --dimension     Dimension to aggregate along (e.g., time)
  --stat          mean | min | max | std | sum  (default: mean)
  --output        table | json  (default: table)
```

```bash
# Mean temperature over time
earthforge cube stats era5.zarr --variable t2m --dimension time --stat mean

# JSON output for scripting
earthforge cube stats era5.zarr --variable t2m --dimension time -o json
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
