"""Metadata inspection for Zarr and NetCDF datacubes.

Opens the store lazily via ``xarray.open_zarr`` or ``xarray.open_dataset``
(with the ``h5netcdf`` engine for NetCDF). No data arrays are loaded into
memory — only the coordinate arrays and top-level attributes are read,
which for consolidated Zarr stores requires a single HTTP request for the
``.zmetadata`` file.

For remote Zarr stores the caller should pass an S3/GCS/Azure URL understood
by ``fsspec``, e.g. ``s3://era5-pds/zarr/``. For local paths, a filesystem
path is accepted as-is.

Usage::

    from earthforge.cube.info import inspect_cube

    info = await inspect_cube("s3://era5-pds/zarr/1979/01/data/eastward_wind.zarr")
    print(f"Variables: {info.variables}")
    print(f"Dimensions: {info.dimensions}")
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from earthforge.cube.errors import CubeError

logger = logging.getLogger(__name__)


class DimensionInfo(BaseModel):
    """Metadata for a single datacube dimension.

    Attributes:
        name: Dimension name (e.g. ``"time"``, ``"latitude"``).
        size: Number of coordinate values along this dimension.
        dtype: NumPy dtype string (e.g. ``"float64"``, ``"datetime64[ns]"``).
        min_value: Minimum coordinate value as a string, if numeric.
        max_value: Maximum coordinate value as a string, if numeric.
        units: CF-convention units attribute, if present.
    """

    name: str = Field(title="Dimension")
    size: int = Field(title="Size")
    dtype: str = Field(title="Dtype")
    min_value: str | None = Field(default=None, title="Min")
    max_value: str | None = Field(default=None, title="Max")
    units: str | None = Field(default=None, title="Units")


class VariableInfo(BaseModel):
    """Metadata for a single datacube variable.

    Attributes:
        name: Variable name.
        dims: Dimension names this variable spans.
        dtype: NumPy dtype string.
        shape: Shape tuple as a list of ints.
        chunks: Chunk shape as a list of ints, if chunked.
        units: CF-convention units attribute, if present.
        long_name: CF-convention long name, if present.
        standard_name: CF-convention standard name, if present.
        fill_value: Missing data fill value as a string, if set.
    """

    name: str = Field(title="Variable")
    dims: list[str] = Field(title="Dimensions")
    dtype: str = Field(title="Dtype")
    shape: list[int] = Field(title="Shape")
    chunks: list[int] | None = Field(default=None, title="Chunks")
    units: str | None = Field(default=None, title="Units")
    long_name: str | None = Field(default=None, title="Long Name")
    standard_name: str | None = Field(default=None, title="Standard Name")
    fill_value: str | None = Field(default=None, title="Fill Value")


class CubeInfo(BaseModel):
    """Structured metadata for a Zarr or NetCDF datacube.

    Attributes:
        source: The store path or URL that was inspected.
        format: Detected format (``"zarr"`` or ``"netcdf"``).
        dimensions: Ordered list of dimension metadata.
        variables: Data variables (excludes coordinate variables).
        global_attrs: Top-level dataset attributes (e.g. CF conventions,
            title, history).
        crs: CRS string extracted from ``crs_wkt`` or ``grid_mapping``
            attributes, if available.
        spatial_bbox: Bounding box ``[west, south, east, north]`` derived
            from ``longitude``/``latitude`` coordinate extents, if available.
        time_range: ``[start, end]`` derived from the ``time`` coordinate
            extents as ISO 8601 strings, if available.
    """

    source: str = Field(title="Source")
    format: str = Field(title="Format")
    dimensions: list[DimensionInfo] = Field(title="Dimensions")
    variables: list[VariableInfo] = Field(title="Variables")
    global_attrs: dict[str, Any] = Field(default_factory=dict, title="Global Attributes")
    crs: str | None = Field(default=None, title="CRS")
    spatial_bbox: list[float] | None = Field(default=None, title="Spatial Bbox")
    time_range: list[str] | None = Field(default=None, title="Time Range")


def _open_zarr(source: str) -> Any:
    """Open a Zarr store lazily with xarray.

    Parameters:
        source: Zarr store path or URL.

    Returns:
        ``xarray.Dataset`` (lazy, no data loaded).

    Raises:
        CubeError: If the store cannot be opened.
    """
    try:
        import xarray as xr
    except ImportError as exc:
        raise CubeError("xarray is required: pip install earthforge[cube]") from exc

    try:
        return xr.open_zarr(source, consolidated=True, chunks=None)
    except Exception:
        # Try without consolidated=True (older or non-consolidated stores)
        try:
            return xr.open_zarr(source, consolidated=False, chunks=None)
        except Exception as exc2:
            raise CubeError(f"Cannot open Zarr store '{source}': {exc2}") from exc2


def _open_netcdf(source: str) -> Any:
    """Open a NetCDF file lazily with xarray using h5netcdf.

    Parameters:
        source: Path to a NetCDF file.

    Returns:
        ``xarray.Dataset`` (lazy, no data loaded).

    Raises:
        CubeError: If the file cannot be opened.
    """
    try:
        import xarray as xr
    except ImportError as exc:
        raise CubeError("xarray is required: pip install earthforge[cube]") from exc

    try:
        return xr.open_dataset(source, engine="h5netcdf", chunks=None)
    except Exception as exc:
        raise CubeError(f"Cannot open NetCDF file '{source}': {exc}") from exc


def _extract_dimension_info(ds: Any, dim_name: str) -> DimensionInfo:
    """Extract metadata for a single coordinate dimension.

    Parameters:
        ds: Open ``xarray.Dataset``.
        dim_name: Name of the dimension to inspect.

    Returns:
        :class:`DimensionInfo` with extent and units extracted from
        coordinate arrays without loading the full data into memory.
    """
    size = ds.sizes[dim_name]
    dtype_str = "unknown"
    min_val: str | None = None
    max_val: str | None = None
    units: str | None = None

    if dim_name in ds.coords:
        coord = ds.coords[dim_name]
        dtype_str = str(coord.dtype)
        units = coord.attrs.get("units")

        try:
            # .values triggers a minimal compute for coordinate arrays only
            vals = coord.values
            if vals.size > 0:
                min_val = str(vals.min())
                max_val = str(vals.max())
        except Exception as _exc:
            logger.debug("Best-effort metadata extraction failed: %s", _exc)

    return DimensionInfo(
        name=dim_name,
        size=size,
        dtype=dtype_str,
        min_value=min_val,
        max_value=max_val,
        units=units,
    )


def _extract_variable_info(ds: Any, var_name: str) -> VariableInfo:
    """Extract metadata for a single data variable.

    Parameters:
        ds: Open ``xarray.Dataset``.
        var_name: Name of the variable to inspect.

    Returns:
        :class:`VariableInfo` with shape, chunk, and CF attributes.
    """
    var = ds[var_name]
    attrs = var.attrs

    chunks: list[int] | None = None
    if hasattr(var, "chunks") and var.chunks:
        # var.chunks is a tuple of tuples — take first chunk size in each dim
        chunks = [c[0] for c in var.chunks]

    fill_val: str | None = None
    if "_FillValue" in attrs:
        fill_val = str(attrs["_FillValue"])
    elif "missing_value" in attrs:
        fill_val = str(attrs["missing_value"])

    return VariableInfo(
        name=var_name,
        dims=list(var.dims),
        dtype=str(var.dtype),
        shape=list(var.shape),
        chunks=chunks,
        units=attrs.get("units"),
        long_name=attrs.get("long_name"),
        standard_name=attrs.get("standard_name"),
        fill_value=fill_val,
    )


def _build_cube_info(source: str, fmt: str, ds: Any) -> CubeInfo:
    """Build a :class:`CubeInfo` from an open xarray Dataset.

    Parameters:
        source: Original store path/URL (for the ``source`` field).
        fmt: Format string (``"zarr"`` or ``"netcdf"``).
        ds: Open ``xarray.Dataset`` (lazy).

    Returns:
        Fully populated :class:`CubeInfo`.
    """
    # Dimensions
    dimensions = [_extract_dimension_info(ds, d) for d in ds.dims]

    # Data variables (not coordinate variables)
    coord_names = set(ds.coords)
    variables = [
        _extract_variable_info(ds, v)
        for v in ds.data_vars
        if v not in coord_names
    ]

    # Global attributes — keep only JSON-serializable scalars/strings
    global_attrs: dict[str, Any] = {}
    for k, v in ds.attrs.items():
        if isinstance(v, (str, int, float, bool)):
            global_attrs[k] = v

    # Derive spatial bbox from lat/lon coordinates
    spatial_bbox: list[float] | None = None
    lon_names = ("longitude", "lon", "x")
    lat_names = ("latitude", "lat", "y")
    lon_coord = next((n for n in lon_names if n in ds.coords), None)
    lat_coord = next((n for n in lat_names if n in ds.coords), None)
    if lon_coord and lat_coord:
        try:
            lons = ds.coords[lon_coord].values
            lats = ds.coords[lat_coord].values
            spatial_bbox = [
                float(lons.min()),
                float(lats.min()),
                float(lons.max()),
                float(lats.max()),
            ]
        except Exception as _exc:
            logger.debug("Best-effort metadata extraction failed: %s", _exc)

    # Derive time range
    time_range: list[str] | None = None
    if "time" in ds.coords:
        try:
            import pandas as pd

            times = ds.coords["time"].values
            if len(times) >= 1:
                time_range = [
                    pd.Timestamp(times[0]).isoformat(),
                    pd.Timestamp(times[-1]).isoformat(),
                ]
        except Exception as _exc:
            logger.debug("Best-effort metadata extraction failed: %s", _exc)

    # Attempt CRS extraction from grid_mapping variable
    crs: str | None = None
    for var_name in ds.data_vars:
        gm = ds[var_name].attrs.get("grid_mapping")
        if gm and gm in ds:
            gm_var = ds[gm]
            wkt = gm_var.attrs.get("crs_wkt") or gm_var.attrs.get("spatial_ref")
            if wkt:
                # Return first 80 chars — full WKT is too long for display
                crs = wkt[:80] if len(wkt) > 80 else wkt
            break

    return CubeInfo(
        source=source,
        format=fmt,
        dimensions=dimensions,
        variables=variables,
        global_attrs=global_attrs,
        crs=crs,
        spatial_bbox=spatial_bbox,
        time_range=time_range,
    )


def _inspect_cube_sync(source: str) -> CubeInfo:
    """Synchronous implementation of cube inspection.

    Detects the format from the source path: ``.zarr`` suffix or directory
    with ``.zmetadata`` → Zarr; otherwise attempts NetCDF.

    Parameters:
        source: Store path or URL.

    Returns:
        :class:`CubeInfo` metadata result.

    Raises:
        CubeError: If the store cannot be opened or format is unrecognized.
    """
    import os

    source_lower = source.lower().rstrip("/")

    # Detect format
    is_zarr = (
        source_lower.endswith(".zarr")
        or source_lower.endswith(".zarr/")
        or (os.path.isdir(source) and os.path.exists(os.path.join(source, ".zmetadata")))
        or (os.path.isdir(source) and os.path.exists(os.path.join(source, ".zarray")))
        or source.startswith("s3://")
        or source.startswith("gs://")
        or source.startswith("az://")
        or source.startswith("abfs://")
    )

    is_netcdf = not is_zarr and (
        source_lower.endswith(".nc")
        or source_lower.endswith(".nc4")
        or source_lower.endswith(".h5")
        or source_lower.endswith(".hdf5")
        or source_lower.endswith(".he5")
    )

    if is_zarr:
        ds = _open_zarr(source)
        fmt = "zarr"
    elif is_netcdf:
        ds = _open_netcdf(source)
        fmt = "netcdf"
    else:
        # Try Zarr first, then NetCDF
        try:
            ds = _open_zarr(source)
            fmt = "zarr"
        except CubeError:
            try:
                ds = _open_netcdf(source)
                fmt = "netcdf"
            except CubeError as exc:
                raise CubeError(
                    f"Cannot determine format for '{source}'. "
                    "Expected .zarr/.nc/.nc4/.h5 or a remote Zarr store URL."
                ) from exc

    try:
        result = _build_cube_info(source, fmt, ds)
    finally:
        try:
            ds.close()
        except Exception as _exc:
            logger.debug("Best-effort metadata extraction failed: %s", _exc)

    return result


async def inspect_cube(source: str) -> CubeInfo:
    """Inspect a Zarr or NetCDF datacube and return structured metadata.

    Opens the store lazily — no data arrays are loaded into memory. For
    consolidated Zarr stores (which include a ``.zmetadata`` file), this
    requires only a single metadata request regardless of how many variables
    the store contains.

    Runs the synchronous xarray/zarr calls in a thread executor to avoid
    blocking the event loop.

    Parameters:
        source: Zarr store path/URL or NetCDF file path. Remote URLs
            (``s3://``, ``gs://``, ``az://``) are passed directly to
            ``xarray.open_zarr`` which delegates to fsspec.

    Returns:
        :class:`CubeInfo` with dimensions, variables, spatial extent,
        time range, and global attributes.

    Raises:
        CubeError: If the store cannot be opened or format is unrecognized.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_inspect_cube_sync, source))
