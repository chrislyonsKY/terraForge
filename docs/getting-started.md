# Getting Started

Get EarthForge running and query your first cloud-native dataset in under 2 minutes.

## Install

```bash
pip install earthforge[all]
```

For GDAL-dependent features (raster convert, vector convert), install via conda for reliable binary dependencies:

```bash
conda install -c conda-forge gdal rasterio pyarrow
pip install earthforge[all]
```

## Initialize Config

```bash
earthforge config init
```

This creates `~/.earthforge/config.toml` with a default profile pointing to [Element84 Earth Search](https://earth-search.aws.element84.com/v1).

## First Query — Inspect a File

EarthForge auto-detects the format. No flags needed:

```bash
# A Cloud Optimized GeoTIFF
earthforge info s3://sentinel-cogs/sentinel-s2-l2a-cogs/10/T/EK/2024/6/S2A_10TEK_20240601_0_L2A/B04.tif

# A local GeoParquet file
earthforge info buildings.parquet

# Output as JSON for piping
earthforge info buildings.parquet --output json
```

## Search a STAC Catalog

```bash
# Search Sentinel-2 over Kentucky
earthforge stac search sentinel-2-l2a \
  --bbox -85,37,-84,38 \
  --datetime 2025-06/2025-09 \
  --max-items 5

# Get item metadata
earthforge stac info https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2A_...
```

## Download Assets

```bash
# Fetch specific bands from a STAC item
earthforge stac fetch https://earth-search.../items/S2A_... \
  --assets red,green,blue,nir \
  --output-dir ./data/s2 \
  --parallel 4

# Re-run the same command — already-complete files are skipped (resume)
earthforge stac fetch https://earth-search.../items/S2A_... --assets red,green,blue
```

## Convert Formats

```bash
# Shapefile to GeoParquet
earthforge vector convert parcels.shp --to geoparquet

# GeoTIFF to Cloud Optimized GeoTIFF
earthforge raster convert image.tif --to cog --compression deflate
```

## Validate Cloud-Native Files

```bash
# Check COG compliance
earthforge raster validate scene.tif

# Generate a quicklook preview (reads overview only — no full download)
earthforge raster preview s3://bucket/scene.tif -o preview.png
```

## Query GeoParquet

```bash
# Spatial bbox query — uses predicate pushdown when covering metadata is present
earthforge vector query buildings.parquet \
  --bbox -85,37,-84,38 \
  --columns id,height,geometry \
  --limit 100

# Output as JSON
earthforge vector query buildings.parquet --bbox -85,37,-84,38 --output json
```

## Working with Profiles

Profiles configure which STAC API and cloud storage credentials to use:

```toml
# ~/.earthforge/config.toml

[profiles.default]
stac_api = "https://earth-search.aws.element84.com/v1"
storage = "s3"

[profiles.default.storage_options]
region = "us-west-2"

[profiles.planetary]
stac_api = "https://planetarycomputer.microsoft.com/api/stac/v1"
storage = "azure"
```

```bash
# Use a specific profile
earthforge stac search sentinel-2-l2a --profile planetary
```

## Python Library Usage

Every CLI command is a thin wrapper around an async library function:

```python
import asyncio
from earthforge.core.config import load_profile
from earthforge.stac.search import search_catalog
from earthforge.raster.info import inspect_raster
from earthforge.vector.query import query_features

async def main():
    profile = await load_profile("default")

    # Search STAC
    results = await search_catalog(profile, collections=["sentinel-2-l2a"],
                                   bbox=(-85, 37, -84, 38))

    # Inspect a COG
    info = await inspect_raster("s3://bucket/scene.tif")
    print(f"{info.width}x{info.height}, {info.band_count} bands, {info.crs}")

    # Spatial query on GeoParquet
    features = await query_features("buildings.parquet", bbox=(-85, 37, -84, 38))
    print(f"Found {features.feature_count} buildings")

asyncio.run(main())
```

---

**Next:** [KyFromAbove tutorials](tutorials/dem-hillshade.md) — real Kentucky datasets, end-to-end workflows.
