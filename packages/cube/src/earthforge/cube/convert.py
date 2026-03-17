"""Datacube format conversion — NetCDF to Zarr and vice versa.

Supports rechunking during conversion via xarray's built-in chunking.

Usage::

    from earthforge.cube.convert import convert_cube

    result = await convert_cube("data.nc", "data.zarr")
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from pydantic import BaseModel, Field

from earthforge.cube.errors import CubeError


class CubeConvertResult(BaseModel):
    """Result of a datacube conversion.

    Attributes:
        source: Input path.
        output: Output path.
        source_format: Input format.
        output_format: Output format.
        variables: Variables in the dataset.
        dimensions: Dimensions in the dataset.
        chunks: Chunk sizes if rechunked.
    """

    source: str = Field(title="Source")
    output: str = Field(title="Output")
    source_format: str = Field(title="Source Format")
    output_format: str = Field(title="Output Format")
    variables: list[str] = Field(default_factory=list, title="Variables")
    dimensions: list[str] = Field(default_factory=list, title="Dimensions")
    chunks: dict[str, int] | None = Field(default=None, title="Chunks")


async def convert_cube(
    source: str,
    output: str,
    *,
    chunks: dict[str, int] | None = None,
) -> CubeConvertResult:
    """Convert between NetCDF and Zarr formats.

    Parameters:
        source: Path to input file (NetCDF or Zarr).
        output: Path for output (use ``.zarr`` suffix for Zarr, ``.nc`` for NetCDF).
        chunks: Optional rechunking spec (dimension name -> chunk size).

    Returns:
        A :class:`CubeConvertResult` with conversion details.

    Raises:
        CubeError: If the conversion fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(_convert_sync, source, output, chunks=chunks),
    )


def _detect_format(path: str) -> str:
    """Detect format from path extension."""
    lower = path.lower()
    if lower.endswith(".zarr"):
        return "zarr"
    if lower.endswith((".nc", ".nc4", ".netcdf")):
        return "netcdf"
    p = Path(path)
    if p.is_dir():
        return "zarr"
    return "netcdf"


def _convert_sync(
    source: str,
    output: str,
    *,
    chunks: dict[str, int] | None = None,
) -> CubeConvertResult:
    """Synchronous conversion implementation."""
    try:
        import xarray as xr
    except ImportError as exc:
        raise CubeError(
            "xarray is required for cube conversion: pip install earthforge[cube]"
        ) from exc

    src_fmt = _detect_format(source)
    out_fmt = _detect_format(output)

    try:
        if src_fmt == "zarr":
            try:
                ds = xr.open_zarr(source, consolidated=True)
            except Exception:
                ds = xr.open_zarr(source, consolidated=False)
        else:
            ds = xr.open_dataset(source)
    except Exception as exc:
        raise CubeError(f"Cannot open source: {exc}") from exc

    variables = list(ds.data_vars)
    dimensions = list(ds.dims)

    if chunks:
        ds = ds.chunk(chunks)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if out_fmt == "zarr":
            ds.to_zarr(str(out_path), mode="w", consolidated=True)
        else:
            ds.to_netcdf(str(out_path))
    except Exception as exc:
        raise CubeError(f"Failed to write output: {exc}") from exc
    finally:
        ds.close()

    return CubeConvertResult(
        source=source,
        output=str(out_path),
        source_format=src_fmt,
        output_format=out_fmt,
        variables=variables,
        dimensions=dimensions,
        chunks=chunks,
    )
