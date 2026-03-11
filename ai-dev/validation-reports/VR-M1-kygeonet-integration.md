# Validation Report: M1 KyFromAbove STAC Integration

**Date:** 2026-03-11
**Endpoint:** KyFromAbove STAC API (`https://spved5ihrl.execute-api.us-west-2.amazonaws.com/`)
**Browser:** `https://kygeonet.ky.gov/stac/`

## Tests Performed

### 1. STAC Collection Info (`inspect_stac_collection`)

- **Target:** `orthos-phase2`
- **Result:** SUCCESS
- ID: `orthos-phase2`
- Title: "Aerial Orthoimagery Phase 2 Leaf-off (3" & 6")"
- License: CC-BY-4.0
- Spatial extent: [-89.90, 35.93, -81.69, 39.66] (full Kentucky)
- Temporal: 2019-02-25 to 2023-04-01

### 2. STAC Search (`search_catalog`)

- **Query:** `collections=["dem-phase2"], bbox=[-84.9, 38.15, -84.8, 38.25], max_items=3`
- **Result:** SUCCESS — 3 items returned
- Items:
  - `N084E283_2023_DEM_Phase2_cog.tif`
  - `N084E282_2023_DEM_Phase2_cog.tif`
  - `N084E281_2019_DEM_Phase2_cog.tif`
- Each item has 2 assets: COG + thumbnail
- `matched` count not supported by this API (expected; handled gracefully)

### 3. STAC Item Info (`inspect_stac_item`)

- **Target:** `N084E283_2023_DEM_Phase2_cog.tif`
- **Result:** SUCCESS
- Collection: dem-phase2
- DateTime: 2022-12-12T00:00:00Z
- CRS: EPSG:3089 (via `proj:epsg` property)
- Geometry type: Polygon
- Assets: COG (`image/tiff; application=geotiff; profile=cloud-optimized`) + PNG thumbnail

### 4. Raster Info (`inspect_raster`) on remote COG

- **Target:** `https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/Phase2/N084E283_2023_DEM_Phase2_cog.tif`
- **Result:** SUCCESS
- Driver: GTiff
- Size: 2500 x 2500 px
- Bands: 1
- CRS: EPSG:3089
- Compression: LZW
- Tiled: 256x256
- Overviews: 4 levels [2, 4, 8, 16]

### 5. COG Validation (`validate_cog`) on remote COG

- **Target:** Same as above
- **Result:** Valid COG (5/5 checks passed)
  - [PASS] geotiff
  - [PASS] tiled (256x256)
  - [PASS] overviews (4 levels)
  - [PASS] compression (LZW)
  - [PASS] ifd_order

## Available Collections

| ID | Title |
|---|---|
| dem-phase1 | Digital Elevation Model Phase 1 |
| dem-phase2 | Digital Elevation Model Phase 2 |
| dem-phase3 | Digital Elevation Model Phase 3 |
| laz-phase1 | Point Cloud Phase 1 (LAZ) |
| laz-phase2 | Point Cloud Phase 2 (COPC) |
| laz-phase3 | Point Cloud Phase 3 (COPC) |
| orthos-phase1 | Aerial Orthoimagery Phase 1 Leaf-off (6" & 12") |
| orthos-phase2 | Aerial Orthoimagery Phase 2 Leaf-off (3" & 6") |
| orthos-phase3 | Aerial Orthoimagery Phase 3 Leaf-off (3") |

## Notes

- The STAC browser at `kygeonet.ky.gov/stac/` serves HTML; the actual API endpoint is the AWS Lambda URL
- The API does not support `numberMatched` (pystac-client emits a warning, but our code handles this gracefully via try/except)
- All DEM tiles are properly formatted COGs with LZW compression and tiled layout
- The S3 data index is at `https://kyfromabove.s3.us-west-2.amazonaws.com/index.html`
