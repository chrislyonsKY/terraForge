# Cloud-Native Geospatial Compliance Guardrails

## STAC Specification

- All STAC items produced by EarthForge must validate against the STAC spec (currently v1.0.0 + v1.1.0-beta)
- Required STAC fields are never optional in EarthForge output: `id`, `type`, `geometry`, `bbox`, `properties.datetime`, `links`, `assets`
- STAC search requests must use `pystac-client` for pagination and conformance handling — do not implement manual pagination
- CQL2 filter syntax is preferred over legacy query parameters when the target API supports it

## COG (Cloud Optimized GeoTIFF)

- COG validation must check: internal tiling (not stripped), overview presence, IFD ordering (overviews before main image), and TIFF tag compliance
- COG conversion defaults: deflate compression, 512x512 tile size, overview levels auto-calculated from image dimensions
- COG files produced by EarthForge must pass `rio cogeo validate` without warnings

## GeoParquet

- GeoParquet files must include the `geo` metadata key with: primary geometry column name, geometry types, CRS (PROJJSON), bounding box
- Row group size should be optimized for spatial locality — default 128MB or user-configurable
- Spatial index (bounding box statistics in row group metadata) must be present for any file produced by EarthForge

## Zarr

- Zarr stores produced by EarthForge must include CF-convention metadata (standard_name, units, axis attributes) when applicable
- Chunk sizes must be explicitly set — never rely on Zarr defaults, which optimize for write performance, not read access patterns
- Zarr v2 is the current target; v3 support is tracked but not required for v0.1.0

## FlatGeobuf

- FlatGeobuf files must include the spatial index (Hilbert R-tree) for any file larger than 10MB
- CRS must be embedded in the FlatGeobuf header — do not produce CRS-less FlatGeobuf files

## General

- CRS must be preserved through all transformations. If a transformation changes CRS, the output must declare the new CRS.
- Bounding box coordinates follow the STAC/GeoJSON convention: [west, south, east, north] in WGS84 (EPSG:4326) unless explicitly stated otherwise
- No format conversion should silently drop metadata. If metadata cannot be preserved, warn the user.
