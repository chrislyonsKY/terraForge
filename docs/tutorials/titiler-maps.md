# Tutorial: Web Maps with TiTiler

EarthForge and [TiTiler](https://developmentseed.org/titiler/) are complementary tools. EarthForge discovers, inspects, validates, and converts cloud-native geospatial files. TiTiler serves them as interactive web maps. Together they cover the full workflow from raw data to web visualization.

## How They Fit Together

```
STAC Catalog
    │
    ▼
earthforge stac search → item URLs
    │
    ▼
earthforge raster validate → confirm COG compliance
    │
    ▼
TiTiler → XYZ tile endpoint → Leaflet / MapLibre / QGIS
```

EarthForge does not serve tiles — that is TiTiler's job. EarthForge ensures the COGs TiTiler will serve are valid, inspects their metadata (CRS, band count, overviews), and can convert non-compliant GeoTIFFs into valid COGs before TiTiler ingests them.

## Prerequisites

```bash
pip install earthforge[raster,stac] titiler.core uvicorn
```

## Step 1: Validate a COG Before Serving

TiTiler requires COGs with internal overviews. Use EarthForge to validate before pointing TiTiler at a file:

```bash
earthforge raster validate s3://bucket/scene.tif
```

If validation fails:

```bash
# Convert to a valid COG
earthforge raster convert scene.tif --to cog -o scene_cog.tif --compression deflate

# Validate the output
earthforge raster validate scene_cog.tif
```

## Step 2: Inspect Bands and CRS

Understanding a COG's band layout before setting up a TiTiler color formula:

```bash
earthforge raster info s3://bucket/multispectral.tif --output json | jq '.bands'
```

```json
[
  {"index": 1, "dtype": "uint16", "nodata": null, "description": "B04 (Red)"},
  {"index": 2, "dtype": "uint16", "nodata": null, "description": "B08 (NIR)"},
  {"index": 3, "dtype": "uint16", "nodata": null, "description": "B11 (SWIR)"}
]
```

## Step 3: Launch TiTiler

```python
# titiler_app.py
from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from fastapi import FastAPI

app = FastAPI(title="EarthForge TiTiler Demo")

cog = TilerFactory()
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)
```

```bash
uvicorn titiler_app:app --host 0.0.0.0 --port 8000
```

## Step 4: Build a Tile URL

```bash
# Get the COG URL from STAC search
earthforge stac search orthos-phase3 \
  --bbox -84.88,38.16,-84.83,38.21 \
  --max-items 1 \
  --output json | jq -r '.items[0].assets[0].href'
```

Then construct a TiTiler tile URL:

```
http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png
  ?url=https://kyfromabove.s3.us-west-2.amazonaws.com/imagery/...
  &bidx=1,2,3
  &rescale=0,255
```

## Step 5: Display in MapLibre GL

```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.js"></script>
  <link href="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.css" rel="stylesheet"/>
</head>
<body>
<div id="map" style="width:100%;height:600px;"></div>
<script>
const COG_URL = encodeURIComponent("https://kyfromabove.s3.us-west-2.amazonaws.com/imagery/...");
const TITILER = "http://localhost:8000";

const map = new maplibregl.Map({ container: "map", style: "..." });

map.on("load", () => {
  map.addSource("cog", {
    type: "raster",
    tiles: [`${TITILER}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=${COG_URL}`],
    tileSize: 256,
  });
  map.addLayer({ id: "cog-layer", type: "raster", source: "cog" });
});
</script>
</body>
</html>
```

## STAC-Aware TiTiler

TiTiler also has a STAC endpoint that works directly with the EarthForge-compatible STAC APIs:

```
http://localhost:8000/stac/tiles/WebMercatorQuad/{z}/{x}/{y}.png
  ?url=https://spved5ihrl.execute-api.us-west-2.amazonaws.com/collections/orthos-phase3/items/N097E305_2024_Season1_3IN_cog.tif
  &assets=data
```

## See Also

- [TiTiler documentation](https://developmentseed.org/titiler/)
- [TiTiler + STAC guide](https://developmentseed.org/titiler/advanced/tiler_factories/#stac)
- [EarthForge raster commands](../getting-started.md#validate-cloud-native-files)
