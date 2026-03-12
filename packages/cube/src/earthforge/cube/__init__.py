"""EarthForge datacube operations.

Provides lazy inspection and spatiotemporal slicing for Zarr and NetCDF
datacubes using xarray as the data model layer. All I/O is async-first:
the synchronous xarray/zarr calls run in a thread executor to avoid
blocking the event loop.
"""
