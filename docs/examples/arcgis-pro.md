# ArcGIS Pro Integration

EarthForge runs in the ArcGIS Pro Python environment. Use it to fetch cloud-native data, validate COGs, and convert vector formats — then hand the results off to ArcGIS Pro for further analysis or cartography.

The EarthForge Python Toolbox provides **14 tools** for ArcGIS Pro, covering STAC discovery, raster operations, vector operations, datacube access, and pipeline execution — all accessible from the ArcGIS Pro Geoprocessing pane.

## Why Use EarthForge with ArcGIS Pro?

ArcGIS Pro can read COGs and GeoParquet directly, but it doesn't have tooling for:

- **STAC discovery** — searching cloud catalogs and downloading specific assets
- **COG validation** — verifying a file's internal structure before adding it to a project
- **Format conversion** — converting Shapefiles to GeoParquet with proper geo metadata
- **Predicate pushdown queries** — filtering large GeoParquet files without loading them into memory
- **Band math** — computing NDVI and other indices with a safe expression evaluator
- **Datacube slicing** — extracting spatiotemporal subsets from Zarr/NetCDF without full download
- **Pipeline execution** — running declarative YAML workflows from within ArcGIS Pro

EarthForge handles these tasks from within the ArcGIS Pro Python environment.

## Setup

ArcGIS Pro ships with a managed `conda` environment. Install EarthForge into it:

```bash
# Open ArcGIS Pro Python Command Prompt
# (Start > ArcGIS > Python Command Prompt)

pip install earthforge[stac,raster,vector]
```

!!! note
    GDAL and rasterio are already installed in the ArcGIS Pro Python environment via `arcpy`. EarthForge uses the same GDAL binaries — no conflict.

## Verify Installation

```python
# In ArcGIS Pro's built-in Notebook or the Python Window
import earthforge.core
print(earthforge.core.__version__)

from earthforge.stac.search import search_catalog
print("EarthForge ready")
```

## Toolbox Overview

The EarthForge Python Toolbox (`.pyt`) exposes 14 tools in the ArcGIS Pro Geoprocessing pane:

| Category | Tool | Description |
|----------|------|-------------|
| STAC | Search Catalog | Search STAC APIs with spatial/temporal filters |
| STAC | Fetch Assets | Download assets with parallel resume |
| STAC | Validate Item | Validate STAC items against spec |
| Raster | Inspect COG | Read COG metadata via range requests |
| Raster | Validate COG | Check COG compliance (tiling, overviews) |
| Raster | Convert to COG | Convert GeoTIFF to Cloud Optimized GeoTIFF |
| Raster | Compute Statistics | Min/max/mean/std/histogram for raster bands |
| Raster | Band Math | Safe expression evaluator for NDVI, ratios |
| Vector | Inspect GeoParquet | Schema, CRS, feature count, bbox |
| Vector | Convert to GeoParquet | Shapefile/GeoJSON/GPKG to GeoParquet 1.1.0 |
| Vector | Spatial Query | Predicate pushdown bbox queries |
| Vector | Clip Features | Clip to bbox or geometry |
| Cube | Inspect Datacube | Dimensions, variables, chunks, time range |
| Pipeline | Run Pipeline | Execute declarative YAML workflows |

## Example: Fetch Imagery and Add to Map

```python
import arcpy
import asyncio
from pathlib import Path
from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog
from earthforge.stac.fetch import fetch_assets

# Use Earth Search STAC directly (no config file needed)
profile = EarthForgeProfile(
    name="default",
    stac_api="https://earth-search.aws.element84.com/v1",
    storage_backend="local",
)

# Get the current map extent as a bbox
aprx = arcpy.mp.ArcGISProject("CURRENT")
extent = aprx.activeMap.defaultCamera.getExtent()
bbox = [extent.XMin, extent.YMin, extent.XMax, extent.YMax]

async def fetch_imagery():
    results = await search_catalog(
        profile, collections=["sentinel-2-l2a"], bbox=bbox, max_items=3
    )
    print(f"Found {len(results.items)} tiles in current extent")

    for item in results.items[:1]:  # fetch first tile
        item_url = f"{profile.stac_api}collections/{item.collection}/items/{item.id}"
        result = await fetch_assets(
            profile,
            item_url=item_url,
            output_dir=str(Path(arcpy.env.scratchFolder) / "sentinel2"),
            assets=["red", "green", "blue"],
        )
        print(f"Downloaded: {result.files[0].local_path}")
        return result.files[0].local_path

local_path = asyncio.run(fetch_imagery())

# Add the downloaded file to the ArcGIS Pro map
aprx.activeMap.addDataFromPath(local_path)
print(f"Added {local_path} to map")
```

## Example: Convert Shapefile to GeoParquet

```python
import asyncio
from earthforge.vector.convert import convert_vector
from earthforge.vector.info import inspect_vector

async def convert_and_inspect(shp_path, output_dir):
    result = await convert_vector(shp_path, output=f"{output_dir}/output.parquet")
    print(f"Converted {result.feature_count} features -> {result.output}")
    print(f"CRS: {result.crs}, Bbox: {result.bbox}")

    # Verify the output
    info = await inspect_vector(result.output)
    print(f"GeoParquet: {info.row_count} rows, {info.num_columns} columns")
    return result.output

output = asyncio.run(convert_and_inspect(
    r"C:\data\parcels.shp",
    r"C:\data\parquet"
))

# The GeoParquet can now be added to ArcGIS Pro as a layer
aprx.activeMap.addDataFromPath(output)
```

## Example: Validate COGs Before Adding to Project

ArcGIS Pro can read COGs, but invalid COGs (strip layout, no overviews) will be slow. Validate first:

```python
import asyncio
from earthforge.raster.validate import validate_cog

async def check_cog(path):
    result = await validate_cog(path)
    if result.is_valid:
        print(f"Valid COG: {path}")
        return True
    else:
        print(f"Invalid COG: {path}")
        for check in result.checks:
            if not check.passed:
                print(f"  FAIL: {check.name} -- {check.message}")
        return False

is_valid = asyncio.run(check_cog(r"C:\data\scene.tif"))
if is_valid:
    aprx.activeMap.addDataFromPath(r"C:\data\scene.tif")
```

## Example: Band Math (NDVI) in ArcGIS Pro

```python
import asyncio
from earthforge.raster.calc import band_calc

async def compute_ndvi(input_path, output_path):
    result = await band_calc(
        input_path,
        expression="(B08 - B04) / (B08 + B04)",
        output=output_path,
    )
    print(f"NDVI computed: {result.output}")
    return result.output

ndvi_path = asyncio.run(compute_ndvi(
    r"C:\data\sentinel2_scene.tif",
    r"C:\data\ndvi_output.tif"
))

aprx.activeMap.addDataFromPath(ndvi_path)
```

## ArcGIS Notebook Integration

EarthForge works naturally in ArcGIS Pro Notebooks. Use `await` directly in notebook cells (Jupyter supports `await` at the top level):

```python
# ArcGIS Pro Notebook cell — no asyncio.run() needed
from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog

profile = EarthForgeProfile(
    name="default",
    stac_api="https://earth-search.aws.element84.com/v1",
    storage_backend="local",
)

results = await search_catalog(
    profile,
    collections=["sentinel-2-l2a"],
    bbox=(-85.0, 37.0, -84.0, 38.0),
    max_items=5,
)
print(f"Found {len(results.items)} Sentinel-2 scenes over Kentucky")
```

## Notes

- The ArcGIS Pro Python environment is `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3`
- EarthForge's async functions work in ArcGIS Notebooks via Jupyter's built-in event loop
- For scripts run via ArcPy (not notebooks), use `asyncio.run()` as shown above
- GDAL version in ArcGIS Pro may differ from standalone installations — EarthForge uses GDAL via `osgeo` which ArcGIS Pro provides
- The Python Toolbox (`.pyt`) wraps all 14 tools with ArcGIS Pro parameter dialogs, validation, and progress reporting
