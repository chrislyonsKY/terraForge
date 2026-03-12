"""Spatiotemporal slicing for Zarr and NetCDF datacubes.

Applies bounding box and time range filters to an open xarray Dataset using
label-based indexing (``sel``) and coordinate-based selection (``where``).
The slice operation is lazy until ``.load()`` is called — only the required
chunks are fetched from the remote store.

Sliced data can be written to a local Zarr store or NetCDF file.

Usage::

    from earthforge.cube.slice import slice_cube

    result = await slice_cube(
        source="s3://era5-pds/zarr/",
        variables=["t2m", "u10"],
        bbox=(-85.0, 37.0, -84.0, 38.0),
        time_range="2025-06-01/2025-06-30",
        output="./data/era5_ky_june2025.zarr",
    )
    print(f"Slice size: {result.output_size_bytes:,} bytes")
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from earthforge.cube.errors import CubeError
from earthforge.cube.info import _open_netcdf, _open_zarr

logger = logging.getLogger(__name__)


class SliceResult(BaseModel):
    """Structured result for a datacube slice operation.

    Attributes:
        source: Input store path or URL.
        output: Path to the written output file or store.
        output_format: Format of the output (``"zarr"`` or ``"netcdf"``).
        variables_selected: Variable names included in the slice.
        bbox: Spatial bounding box applied, if any.
        time_range: Time range applied as ``[start, end]`` ISO strings, if any.
        shape: Shape of the output Dataset as ``{dim: size}`` mapping.
        output_size_bytes: Size of the output file/directory in bytes.
        elapsed_seconds: Wall-clock time for the operation.
    """

    source: str = Field(title="Source")
    output: str = Field(title="Output")
    output_format: str = Field(title="Output Format")
    variables_selected: list[str] = Field(title="Variables")
    bbox: list[float] | None = Field(default=None, title="Bbox")
    time_range: list[str] | None = Field(default=None, title="Time Range")
    shape: dict[str, int] = Field(default_factory=dict, title="Shape")
    output_size_bytes: int = Field(default=0, title="Output Size (bytes)")
    elapsed_seconds: float = Field(title="Elapsed (s)")


def _parse_time_range(time_range: str) -> tuple[str, str]:
    """Parse an ISO 8601 date range string into start and end strings.

    Accepts ``YYYY-MM-DD/YYYY-MM-DD`` or ``YYYY-MM/YYYY-MM`` formats.

    Parameters:
        time_range: Date range string with ``/`` separator.

    Returns:
        ``(start, end)`` tuple of date strings.

    Raises:
        CubeError: If the format is invalid.
    """
    parts = time_range.strip().split("/")
    if len(parts) != 2:
        raise CubeError(
            f"Invalid time_range '{time_range}'. Expected ISO 8601 range: "
            "'YYYY-MM-DD/YYYY-MM-DD' or 'YYYY-MM/YYYY-MM'."
        )
    return parts[0].strip(), parts[1].strip()


def _dir_size(path: Path) -> int:
    """Return total size in bytes for a directory tree.

    Parameters:
        path: Directory path.

    Returns:
        Sum of all file sizes under ``path``.
    """
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _apply_bbox(ds: Any, bbox: tuple[float, float, float, float]) -> Any:
    """Clip a Dataset to a bounding box using coordinate masking.

    Uses ``sel`` with ``slice`` for regular grids. Falls back to ``where``
    with boolean masks for irregular grids.

    Parameters:
        ds: Open ``xarray.Dataset``.
        bbox: ``(west, south, east, north)`` in CRS units (usually degrees).

    Returns:
        Dataset clipped to the bbox (lazy, no compute triggered).

    Raises:
        CubeError: If the Dataset has no recognizable spatial coordinates.
    """
    west, south, east, north = bbox
    lon_names = ("longitude", "lon", "x")
    lat_names = ("latitude", "lat", "y")
    lon_dim = next((n for n in lon_names if n in ds.coords), None)
    lat_dim = next((n for n in lat_names if n in ds.coords), None)

    if lon_dim is None or lat_dim is None:
        raise CubeError(
            "Cannot apply bbox: Dataset has no recognizable longitude/latitude "
            f"coordinates. Available coords: {list(ds.coords)}"
        )

    try:
        lons = ds.coords[lon_dim].values
        # Handle 0-360 longitude convention
        if float(lons.max()) > 180 and west < 0:
            west = west + 360
            east = east + 360

        return ds.sel(
            {
                lon_dim: slice(west, east),
                lat_dim: slice(south, north),
            }
        )
    except Exception:
        # Irregular grid: use boolean mask
        try:
            lon_vals = ds.coords[lon_dim]
            lat_vals = ds.coords[lat_dim]
            mask = (
                (lon_vals >= west) & (lon_vals <= east) & (lat_vals >= south) & (lat_vals <= north)
            )
            return ds.where(mask, drop=True)
        except Exception as exc:
            raise CubeError(f"Failed to apply bbox to Dataset: {exc}") from exc


def _apply_time_range(ds: Any, time_range: str) -> Any:
    """Clip a Dataset to a time range.

    Parameters:
        ds: Open ``xarray.Dataset``.
        time_range: ISO 8601 range string (``YYYY-MM-DD/YYYY-MM-DD``).

    Returns:
        Dataset clipped to the time range (lazy).

    Raises:
        CubeError: If no ``time`` coordinate exists or the range is invalid.
    """
    if "time" not in ds.coords:
        raise CubeError(
            f"Cannot apply time_range: Dataset has no 'time' coordinate. "
            f"Available coords: {list(ds.coords)}"
        )

    start, end = _parse_time_range(time_range)
    try:
        return ds.sel(time=slice(start, end))
    except Exception as exc:
        raise CubeError(f"Failed to apply time_range '{time_range}': {exc}") from exc


def _slice_cube_sync(
    source: str,
    variables: list[str] | None,
    bbox: tuple[float, float, float, float] | None,
    time_range: str | None,
    output: str,
    output_format: str,
) -> SliceResult:
    """Synchronous implementation of cube slicing.

    Opens the store, applies filters, loads only the required chunks into
    memory, and writes the result to the specified output path.

    Parameters:
        source: Input store path or URL.
        variables: Variable names to include. If ``None``, all data vars.
        bbox: ``(west, south, east, north)`` spatial filter, or ``None``.
        time_range: ISO 8601 range string, or ``None``.
        output: Output path. Written as Zarr if it ends in ``.zarr``,
            otherwise as NetCDF4.
        output_format: ``"zarr"`` or ``"netcdf"`` (derived from ``output``).

    Returns:
        :class:`SliceResult` describing the output.

    Raises:
        CubeError: On open, filter, load, or write failure.
    """
    t_start = time.perf_counter()

    # Open the dataset
    source_lower = source.lower().rstrip("/")
    is_netcdf = source_lower.endswith((".nc", ".nc4", ".h5", ".hdf5", ".he5"))
    if is_netcdf:
        ds = _open_netcdf(source)
    else:
        ds = _open_zarr(source)

    try:
        # Select variables
        if variables:
            available = list(ds.data_vars)
            missing = [v for v in variables if v not in available]
            if missing:
                raise CubeError(f"Variables not found in store: {missing}. Available: {available}")
            ds = ds[variables]

        # Apply spatial filter
        if bbox is not None:
            ds = _apply_bbox(ds, bbox)

        # Apply time filter
        if time_range is not None:
            ds = _apply_time_range(ds, time_range)

        # Collect selected variable names
        vars_selected = list(ds.data_vars)

        # Record shape before loading
        shape = dict(ds.sizes)

        # Load into memory (triggers data transfer for filtered chunks only)
        logger.debug("Loading slice from %s …", source)
        ds = ds.load()

        # Write output
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == "zarr":
            import shutil

            if out_path.exists():
                shutil.rmtree(out_path)
            ds.to_zarr(str(out_path), mode="w")
        else:
            ds.to_netcdf(str(out_path), engine="h5netcdf")

    finally:
        try:
            ds.close()
        except Exception as _exc:
            logger.debug("Best-effort metadata extraction failed: %s", _exc)

    elapsed = time.perf_counter() - t_start
    output_size = _dir_size(out_path)

    bbox_list = list(bbox) if bbox is not None else None
    tr_list: list[str] | None = None
    if time_range is not None:
        start, end = _parse_time_range(time_range)
        tr_list = [start, end]

    return SliceResult(
        source=source,
        output=str(out_path),
        output_format=output_format,
        variables_selected=vars_selected,
        bbox=bbox_list,
        time_range=tr_list,
        shape=shape,
        output_size_bytes=output_size,
        elapsed_seconds=round(elapsed, 3),
    )


async def slice_cube(
    source: str,
    *,
    variables: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    time_range: str | None = None,
    output: str,
) -> SliceResult:
    """Slice a Zarr or NetCDF datacube by variables, bbox, and time.

    The operation is lazy until the subset is written: xarray defers all
    data transfer until the ``.load()`` call, so only the chunks that
    intersect the requested slice are fetched from the remote store.

    Parameters:
        source: Zarr store path/URL or NetCDF file path.
        variables: Variable names to include. If ``None``, all data variables
            are included.
        bbox: Spatial filter as ``(west, south, east, north)`` in the
            coordinate system of the Dataset (usually degrees for global
            products). If ``None``, no spatial filter is applied.
        time_range: ISO 8601 date range string (``YYYY-MM-DD/YYYY-MM-DD``
            or ``YYYY-MM/YYYY-MM``). If ``None``, no time filter is applied.
        output: Output path. Written as Zarr if the path ends in ``.zarr``;
            otherwise written as NetCDF4 via h5netcdf.

    Returns:
        :class:`SliceResult` with output path, shape, size, and timing.

    Raises:
        CubeError: If the store cannot be opened, variables are missing,
            filter coordinates are absent, or writing fails.
    """
    output_format = "zarr" if output.lower().rstrip("/").endswith(".zarr") else "netcdf"

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _slice_cube_sync,
            source,
            variables,
            bbox,
            time_range,
            output,
            output_format,
        ),
    )
