# STAC Collections

EarthForge works with any STAC-compliant API. This page lists well-known public STAC catalogs, their collections, and example commands to get started.

## Configuring a STAC Profile

```toml
# ~/.earthforge/config.toml

[profiles.default]
stac_api = "https://earth-search.aws.element84.com/v1"
storage = "s3"
[profiles.default.storage_options]
region = "us-east-1"

[profiles.planetary]
stac_api = "https://planetarycomputer.microsoft.com/api/stac/v1"
storage = "azure"

[profiles.kyfromabove]
stac_api = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com/"
storage = "s3"
[profiles.kyfromabove.storage_options]
region = "us-west-2"
```

---

## Element84 Earth Search (default)

**Endpoint:** `https://earth-search.aws.element84.com/v1`
**Host:** Amazon Web Services / Element84
**Coverage:** Global

| Collection | Description |
|-----------|-------------|
| `sentinel-2-l2a` | Sentinel-2 Level 2A (10m, multispectral, global) |
| `sentinel-2-l1c` | Sentinel-2 Level 1C (top-of-atmosphere) |
| `landsat-c2-l2` | Landsat Collection 2 Level 2 (30m, global) |
| `cop-dem-glo-30` | Copernicus DEM 30m (global elevation) |
| `cop-dem-glo-90` | Copernicus DEM 90m (global elevation) |
| `naip` | USDA NAIP (1m aerial, continental US) |

```bash
earthforge stac search sentinel-2-l2a \
  --bbox -85,37,-84,38 --datetime 2025-06/2025-09 --max-items 5

earthforge stac search cop-dem-glo-30 --bbox -85,37,-84,38
```

---

## Microsoft Planetary Computer

**Endpoint:** `https://planetarycomputer.microsoft.com/api/stac/v1`
**Coverage:** Global; some collections require token signing

| Collection | Description |
|-----------|-------------|
| `sentinel-2-l2a` | Sentinel-2 Level 2A |
| `landsat-c2-l2` | Landsat Collection 2 |
| `io-lulc-9-class` | Impact Observatory 10m global land use/land cover |
| `3dep-lidar-copc` | USGS 3DEP LiDAR (COPC format) |
| `era5-pds` | ERA5 climate reanalysis (Zarr) |
| `goes-cmi` | GOES-16/17/18 satellite imagery |
| `modis-*` | MODIS land cover, vegetation, fire products |

```bash
earthforge stac search sentinel-2-l2a --bbox -105,40,-104,41 --profile planetary
earthforge stac search era5-pds --profile planetary
```

---

## USGS 3DEP LiDAR

**Endpoint:** `https://stac.lidar.earthdatascience.org/`
**Coverage:** Continental US
**Format:** COPC (Cloud Optimized Point Cloud)

```bash
earthforge stac search 3dep-lidar-copc \
  --bbox -105.1,40.5,-104.9,40.7 --profile usgs3dep
```

---

## KyFromAbove (Kentucky Statewide)

**Endpoint:** `https://spved5ihrl.execute-api.us-west-2.amazonaws.com/`
**Coverage:** Commonwealth of Kentucky
**License:** Public domain

| Collection | Type | Resolution |
|-----------|------|------------|
| `orthos-phase3` | Aerial orthoimagery COG | 3" (2022–present) |
| `orthos-phase2` | Aerial orthoimagery COG | 3"/6" (2016–2022) |
| `orthos-phase1` | Aerial orthoimagery COG | 6"/12" (2012–2016) |
| `dem-phase3` | Digital Elevation Model COG | 2ft (2022–present) |
| `dem-phase2` | Digital Elevation Model COG | 2ft (2016–2022) |
| `dem-phase1` | Digital Elevation Model COG | 5ft (2010–2016) |
| `laz-phase3` | LiDAR point cloud (COPC) | 2022–present |
| `laz-phase2` | LiDAR point cloud (COPC) | 2016–2022 |
| `laz-phase1` | LiDAR point cloud (LAZ) | 2010–2016 |

All datasets are hosted on S3 (`kyfromabove.s3.us-west-2.amazonaws.com`) and publicly accessible with no authentication.

---

## NOAA / Weather

Many NOAA datasets are accessible as Zarr or NetCDF:

```bash
# GOES-16 ABI via Planetary Computer
earthforge stac search goes-cmi --profile planetary

# ERA5 reanalysis (Zarr)
earthforge cube info s3://era5-pds/zarr/1979/01/data/eastward_wind.zarr
```

---

## Building a Custom Profile

Any STAC 1.0-compliant API works:

```bash
earthforge config set profiles.custom.stac_api https://your-api.example.com/
earthforge stac info https://your-api.example.com/ --profile custom
```

EarthForge uses `pystac-client` for STAC interactions — conformance negotiation, pagination, and CQL2 filter support are handled automatically.
