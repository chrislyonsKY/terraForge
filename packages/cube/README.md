# earthforge-cube

Zarr and NetCDF datacube inspection and slicing for EarthForge.

```bash
earthforge cube info s3://era5-pds/zarr/1979/01/data/eastward_wind.zarr
earthforge cube slice s3://era5-pds/zarr/ --var t2m --bbox -85,37,-84,38 --time 2025-06
```
