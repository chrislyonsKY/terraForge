# EarthForge

**Cloud-native geospatial developer toolkit.**

Working with cloud-native geospatial data means juggling `gdalinfo` for COGs, `stac-client` for discovery,
`geopandas` for GeoParquet, and `xarray` for Zarr — each with its own conventions, output format, and
authentication story.

EarthForge is one composable toolkit that unifies these workflows. One CLI. One config system. One output contract.
Every command works locally and against S3, GCS, or Azure. Every command produces both human-readable tables
and machine-parseable JSON.

---

## Install

=== "pip"

    ```bash
    pip install earthforge[all]
    ```

=== "conda + pip"

    GDAL-dependent features (raster convert, vector convert) need reliable binary builds:

    ```bash
    conda install -c conda-forge gdal rasterio pyarrow
    pip install earthforge[all]
    ```

=== "extras only"

    Install only what you need:

    ```bash
    pip install earthforge[stac]    # STAC discovery
    pip install earthforge[raster]  # COG operations
    pip install earthforge[vector]  # GeoParquet operations
    pip install earthforge[cube]    # Zarr datacube
    ```

---

## Quick Start

```bash
# Inspect any cloud-native file — format auto-detected
earthforge info s3://sentinel-cogs/sentinel-s2-l2a-cogs/10/T/EK/2024/6/S2A_10TEK_20240601_0_L2A/B04.tif
earthforge info buildings.parquet
earthforge info climate.zarr

# Search a STAC catalog
earthforge stac search sentinel-2-l2a \
  --bbox -85,37,-84,38 \
  --datetime 2025-06/2025-09

# Convert legacy formats to cloud-native
earthforge vector convert parcels.shp --to geoparquet
earthforge raster convert image.tif --to cog

# Query GeoParquet with predicate pushdown
earthforge vector query buildings.parquet --bbox -85,37,-84,38

# Pipe JSON into other tools
earthforge stac search sentinel-2-l2a -o json | jq '.items[].assets.B04.href'
```

---

## Supported Formats

| Format | Support | Commands |
|--------|---------|----------|
| COG (Cloud Optimized GeoTIFF) | Full | `info`, `validate`, `convert`, `preview` |
| GeoParquet | Full | `info`, `convert`, `query` |
| Zarr / NetCDF | Full | `info`, `slice` |
| FlatGeobuf | Read/Write | `info`, `convert` |
| STAC | Full | `search`, `info`, `fetch` |
| COPC (Cloud Optimized Point Cloud) | Detection | `info` |

---

## What EarthForge Is Not

EarthForge is **not** a platform, web server, tile cache, database, or ML pipeline.
It is not a replacement for QGIS, ArcGIS, or Google Earth Engine.

If you need a tile server, use [TiTiler](https://developmentseed.org/titiler/).
If you need a STAC API, use [stac-fastapi](https://github.com/stac-utils/stac-fastapi).
EarthForge is the CLI toolkit you reach for *alongside* those tools.

---

## Python Library

Every CLI command is a thin wrapper around an async library function:

```python
import asyncio
from earthforge.core.config import load_profile
from earthforge.stac.search import search_catalog
from earthforge.raster.info import inspect_raster

async def main():
    profile = await load_profile("default")
    items = await search_catalog(profile, collections=["sentinel-2-l2a"],
                                 bbox=(-85, 37, -84, 38))
    info = await inspect_raster("s3://bucket/scene.tif")
    print(f"{info.width}x{info.height}, {info.band_count} bands")

asyncio.run(main())
```

---

[Get started →](getting-started.md){ .md-button .md-button--primary }
[CLI Reference →](cli.md){ .md-button }
