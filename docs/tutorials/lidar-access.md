# Tutorial: LiDAR / Point Cloud Access (COPC)

Access Cloud Optimized Point Clouds (COPC) via STAC without downloading entire LAZ files. COPC stores a spatially indexed octree inside a standard LAZ container, enabling HTTP range requests to retrieve only the points in your area of interest.

EarthForge detects COPC files via the `LASF` magic bytes and the COPC VLR signature. Full point cloud processing (filtering, classification, ground extraction) is handled by downstream tools like [PDAL](https://pdal.io/) or [laspy](https://laspy.readthedocs.io/) — EarthForge handles discovery, inspection, and fetch.

## Prerequisites

```bash
pip install earthforge[stac]

# For point cloud processing (optional)
conda install -c conda-forge pdal python-pdal
pip install laspy[lazrs]
```

## Step 1: Discover COPC Tiles

EarthForge works with any STAC API that has COPC assets. Examples include:

- **KyFromAbove** — `laz-phase2`, `laz-phase3` (Kentucky statewide)
- **USGS 3DEP** — national LiDAR program, multiple STAC endpoints
- **OpenTopography** — global point cloud repository

```bash
# Search KyFromAbove COPC over Louisville, KY
earthforge stac search laz-phase3 \
  --bbox -85.80,38.20,-85.70,38.30 \
  --max-items 5

# Search USGS 3DEP
earthforge stac search 3dep-lidar-copc \
  --bbox -105.1,40.5,-104.9,40.7 \
  --max-items 3 \
  --profile usgs
```

## Step 2: Inspect the Point Cloud Asset

```bash
# Detect format — EarthForge recognizes LASF magic bytes
earthforge info <copc-laz-url>

# Output
# Source   N097E302_LAS_Phase3.copc
# Format   copc
```

!!! note
    Full COPC metadata inspection (point count, density, coordinate bounds, VLR contents) is on the M4 roadmap. The current `info` command detects the format and reports file size and last-modified. Use `pdal info` or `laspy` for deep point cloud inspection.

## Step 3: Fetch a COPC Tile

```bash
earthforge stac fetch <item-url> \
  --assets pointcloud \
  --output-dir ./data/lidar \
  --parallel 2
```

COPC files range from 200 MB to 2 GB depending on point density. The fetch command streams the download and supports resume — if interrupted, re-running will skip the already-downloaded bytes.

## Step 4: Process with PDAL

Once downloaded, use PDAL for point cloud operations:

```bash
# Clip to a bounding box
pdal pipeline - <<EOF
{
  "pipeline": [
    { "type": "readers.copc",
      "filename": "data/lidar/N097E302_LAS_Phase3.copc",
      "bounds": "([-85.80, -85.75], [38.20, 38.25])" },
    { "type": "filters.range",
      "limits": "Classification[2:2]" },
    { "type": "writers.las",
      "filename": "data/lidar/ground_only.las" }
  ]
}
EOF

# Rasterize to DEM at 1-meter resolution
pdal pipeline - <<EOF
{
  "pipeline": [
    "data/lidar/ground_only.las",
    { "type": "writers.gdal",
      "filename": "data/lidar/dem_1m.tif",
      "resolution": 1.0,
      "output_type": "mean" }
  ]
}
EOF
```

## Step 5: Convert the Derived DEM to COG

```bash
earthforge raster convert data/lidar/dem_1m.tif --to cog -o data/lidar/dem_1m_cog.tif
earthforge raster validate data/lidar/dem_1m_cog.tif
```

## Pipeline Approach

For batch processing multiple COPC tiles, combine EarthForge fetch with PDAL:

```python
import asyncio
from earthforge.core.config import load_profile
from earthforge.stac.search import search_catalog
from earthforge.stac.fetch import fetch_assets

async def batch_fetch_copc(bbox, collection="laz-phase3", profile_name="kyfromabove"):
    profile = await load_profile(profile_name)
    results = await search_catalog(profile, collections=[collection], bbox=bbox)
    print(f"Fetching {len(results.items)} COPC tiles...")

    for item in results.items:
        result = await fetch_assets(
            profile,
            item_url=f".../{item.id}",
            output_dir=f"data/lidar/{item.id}",
            assets=["pointcloud"],
            parallel=2,
        )
        print(f"  {item.id}: {result.total_bytes_downloaded:,} bytes")

asyncio.run(batch_fetch_copc(bbox=(-85.80, 38.20, -85.70, 38.30)))
```

## See Also

- [PDAL documentation](https://pdal.io/en/stable/)
- [COPC specification](https://copc.io/)
- [KyFromAbove collections](../stac-collections.md)
