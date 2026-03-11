# Cloud-Native Geospatial Formats Skill

## COG — Reading Only What You Need

The core principle of COG access is **partial reads via HTTP range requests**. Never download a full COG to read a subset.

### Reading a preview from a remote COG

```python
import rasterio

# rasterio's /vsicurl/ driver handles range requests automatically
with rasterio.open("https://example.com/image.tif") as dataset:
    # Read at overview level — NOT full resolution
    # overview_level=0 is the coarsest overview
    overviews = dataset.overviews(1)  # overview levels for band 1

    if overviews:
        # Calculate target shape from the coarsest overview
        overview_factor = overviews[-1]  # largest reduction factor
        target_h = dataset.height // overview_factor
        target_w = dataset.width // overview_factor

        # This issues range requests for only the overview tiles needed
        data = dataset.read(out_shape=(dataset.count, target_h, target_w))
    else:
        # No overviews — this file is not a proper COG
        # Fall back to subsampled read (still uses range requests for tiled TIFFs)
        data = dataset.read(out_shape=(dataset.count, 256, 256))
```

### COG validation checks

```python
def is_valid_cog(path: str) -> tuple[bool, list[str]]:
    """Check COG compliance. Returns (is_valid, list_of_warnings)."""
    import rasterio

    warnings = []
    with rasterio.open(path) as ds:
        # Check 1: Must be tiled (not stripped)
        if not ds.is_tiled:
            warnings.append("Not tiled — image uses strip layout")

        # Check 2: Must have overviews
        overviews = ds.overviews(1)
        if not overviews:
            warnings.append("No overviews — zoom-level reads will require full resolution")

        # Check 3: IFD ordering (overviews before main image)
        # This requires reading the TIFF IFD chain directly
        # rasterio doesn't expose this; use GDAL's COG validation or byte inspection

    is_valid = len(warnings) == 0
    return is_valid, warnings
```

## GeoParquet — Predicate Pushdown

### Spatial query with row-group filtering

```python
import geopandas as gpd

# ✅ CORRECT — bbox pushdown skips non-intersecting row groups
gdf = gpd.read_parquet("buildings.parquet", bbox=(-85, 37, -84, 38))

# ❌ WRONG — reads ALL data, then filters in memory
gdf = gpd.read_parquet("buildings.parquet")
gdf = gdf.cx[-85:-84, 37:38]
```

### Inspecting GeoParquet metadata without reading data

```python
import pyarrow.parquet as pq

metadata = pq.read_metadata("buildings.parquet")
geo_meta = json.loads(metadata.metadata[b"geo"])

# geo_meta contains:
# - primary_column: name of the geometry column
# - columns: {column_name: {encoding, geometry_types, crs, bbox}}
# - crs is PROJJSON format
```

## Zarr — Lazy Loading

### Inspect without loading

```python
import xarray as xr

# ✅ CORRECT — lazy open, no data loaded
ds = xr.open_zarr("climate.zarr")
print(ds)  # shows dimensions, variables, chunks — zero data read

# Extract a slice — only the needed chunks are read
subset = ds.sel(time="2025-06", lat=slice(37, 38), lon=slice(-85, -84))
data = subset.load()  # THIS is when data transfers happen

# ❌ WRONG — loads entire dataset into memory
ds = xr.open_zarr("climate.zarr").load()
```

### Rechunking for different access patterns

```python
# Original: optimized for spatial snapshots
# chunks: time=1, lat=1024, lon=1024

# Rechunk for time-series analysis at a point
ds_rechunked = ds.chunk({"time": 365, "lat": 1, "lon": 1})
ds_rechunked.to_zarr("climate_timeseries.zarr")
```

## FlatGeobuf — Streaming and Spatial Index

FlatGeobuf includes a Hilbert R-tree spatial index. For files >10MB, the index is essential for spatial queries. The index enables HTTP range requests for spatial subsets, similar to COG tile access.

## COPC — Cloud Optimized Point Clouds

COPC (Cloud Optimized Point Cloud) is to LAZ what COG is to GeoTIFF — an internal organization that enables spatial and level-of-detail queries via range requests. COPC uses an octree index embedded in a LAZ 1.4 container.

Reading COPC in Python uses `laspy` or `pdal`:
```python
import laspy

# laspy supports COPC range reads for spatial subsets
with laspy.open("pointcloud.copc.laz") as reader:
    # Read metadata without loading points
    header = reader.header
    # point_count, crs, bbox, etc.
```
