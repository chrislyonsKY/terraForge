# EarthForge

**Cloud-native geospatial developer toolkit.**

Working with cloud-native geospatial data means juggling `gdalinfo` for COGs, `stac-client` for discovery, `geopandas` for GeoParquet, `xarray` for Zarr, and a collection of one-off scripts to glue them together. Each tool has its own CLI conventions, its own output format, and its own assumptions about how you authenticate to cloud storage.

EarthForge is a single composable toolkit that unifies these workflows.

```bash
# Inspect any cloud-native geospatial file — format auto-detected
earthforge info s3://bucket/scene.tif
earthforge info buildings.parquet
earthforge info climate.zarr

# Search STAC catalogs
earthforge stac search sentinel-2-l2a --bbox -85,37,-84,38 --datetime 2025-06/2025-09

# Download assets with resume support
earthforge stac fetch https://earth-search.../items/S2A_... --assets red,green,blue

# Convert legacy formats to cloud-native
earthforge vector convert parcels.shp --to geoparquet
earthforge raster convert image.tif --to cog

# Query GeoParquet with predicate pushdown
earthforge vector query buildings.parquet --bbox -85,37,-84,38

# Pipe JSON into other tools
earthforge stac search sentinel-2-l2a -o json | jq '.items[].assets.B04.href'
```

## What EarthForge Is

A **library-first, CLI-first** developer toolkit. Install it as a Python library and call functions directly, or use the CLI from shell scripts and pipelines. Every CLI command is a thin wrapper around a library function.

```python
from earthforge.raster.info import inspect_raster
from earthforge.stac.search import search_catalog

items = await search_catalog(profile, collections=["sentinel-2-l2a"], bbox=(-85, 37, -84, 38))
metadata = await inspect_raster("s3://bucket/scene.tif")
```

## What EarthForge Is Not

EarthForge is **not** a platform, a web server, a tile cache, a database, or an ML pipeline. It is not a replacement for QGIS, ArcGIS, or Google Earth Engine.

If you need a tile server, use [TiTiler](https://developmentseed.org/titiler/). If you need a STAC API, use [stac-fastapi](https://github.com/stac-utils/stac-fastapi). EarthForge is the CLI toolkit you reach for *alongside* those tools.

## Supported Formats

| Format | Support | Commands |
|--------|---------|----------|
| COG (Cloud Optimized GeoTIFF) | Full | info, validate, convert, preview |
| GeoParquet | Full | info, convert, query |
| Zarr | Full | info, slice |
| FlatGeobuf | Read/Write | info, convert |
| STAC | Full | search, info, fetch |
| COPC (Cloud Optimized Point Cloud) | Detection | info |

## Install

```bash
pip install earthforge[all]          # Everything
pip install earthforge[stac]         # STAC discovery only
pip install earthforge[raster]       # COG operations only
pip install earthforge[vector]       # GeoParquet operations only
pip install earthforge[cube]         # Zarr datacube operations only
```

---

[Get started in 2 minutes →](getting-started.md)
