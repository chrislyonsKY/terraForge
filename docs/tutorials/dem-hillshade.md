# Tutorial: DEM Hillshade from KyFromAbove

Create a hillshade visualization from Kentucky's 2-foot Digital Elevation Model using EarthForge and GDAL. This workflow uses cloud-native COG assets — the full DEM tile is only downloaded if you need it locally; you can inspect the metadata and preview it from the cloud.

**Location:** Frankfort, KY (state capital)
**Dataset:** `dem-phase3` — 2-foot resolution, leaf-off, NAVD88 elevation in feet

## Prerequisites

```bash
pip install earthforge[raster,stac]
conda install -c conda-forge gdal  # for hillshade generation
```

## Step 1: Find the DEM Tile

```bash
# Search for DEM tiles over Frankfort
earthforge stac search dem-phase3 \
  --bbox -84.88,38.16,-84.83,38.21 \
  --max-items 3
```

Sample output:
```
Item ID                              Datetime    Collection
N097E304_DEM_Phase3.tif             2024-01-01  dem-phase3
N097E305_DEM_Phase3.tif             2024-01-01  dem-phase3
```

```bash
# Inspect the COG without downloading it
earthforge raster info <item-data-href>
```

```
Source    N097E304_DEM_Phase3.tif
Driver    GTiff
Width     10000
Height    10000
CRS       EPSG:3089
Bands     1
Dtype     float32
Tiled     True  (512×512)
Overviews 4
Compress  DEFLATE
```

## Step 2: Validate COG Compliance

```bash
earthforge raster validate <item-data-href>
```

```
Check      Passed  Detail
geotiff    True    File is a GeoTIFF
tiled      True    Tiled layout (block=512×512)
overviews  True    Overviews present (levels=[2, 4, 8, 16])
compress   True    Compressed (DEFLATE)
ifd_order  True    IFD ordering OK
```

## Step 3: Generate a Quicklook

```bash
# Read overview level only — no full download
earthforge raster preview <item-data-href> \
  --max-size 512 \
  -o frankfort_dem_preview.png
```

## Step 4: Download the Full Tile

```bash
# Fetch the DEM COG via stac fetch
earthforge stac fetch <item-url> \
  --assets data \
  --output-dir ./data/frankfort_dem
```

## Step 5: Generate Hillshade

With the DEM downloaded, use GDAL to generate a hillshade:

```bash
gdaldem hillshade \
  data/frankfort_dem/N097E304_DEM_Phase3.tif \
  frankfort_hillshade.tif \
  -az 315 -alt 45 \
  -co COMPRESS=DEFLATE \
  -co TILED=YES \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512
```

Convert the hillshade to a shareable COG:

```bash
earthforge raster convert frankfort_hillshade.tif --to cog -o frankfort_hillshade_cog.tif
earthforge raster validate frankfort_hillshade_cog.tif
```

## Python Library Version

```python
import asyncio
from pathlib import Path
from earthforge.core.config import load_profile
from earthforge.stac.search import search_catalog
from earthforge.stac.fetch import fetch_assets
from earthforge.raster.info import inspect_raster
from earthforge.raster.validate import validate_cog

async def main():
    profile = await load_profile("kyfromabove")

    # Find the tile
    results = await search_catalog(
        profile,
        collections=["dem-phase3"],
        bbox=(-84.88, 38.16, -84.83, 38.21),
        max_items=1,
    )
    item = results.items[0]
    print(f"Found: {item.id}")

    # Inspect without downloading
    data_asset = next(a for a in item.assets if a.key == "data")
    info = await inspect_raster(data_asset.href)
    print(f"Size: {info.width}x{info.height}, {info.overview_count} overviews")

    # Download
    fetch_result = await fetch_assets(
        profile,
        item_url=f".../{item.id}",
        output_dir="./data/dem",
        assets=["data"],
    )
    print(f"Downloaded: {fetch_result.total_bytes_downloaded:,} bytes")

asyncio.run(main())
```

## Notes

- KyFromAbove DEMs are in KY SCOS (EPSG:3089) with elevations in feet above NAVD88
- Phase 3 tiles cover approximately 5000×5000 feet at 2-foot resolution (10,000×10,000 pixels)
- Overviews allow `raster preview` to generate a thumbnail in <2 seconds without touching the full 400MB tile
