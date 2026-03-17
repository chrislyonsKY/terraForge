"""Datacube aggregate statistics along dimensions.

Computes summary statistics (mean, min, max, std, sum) over specified
dimensions using xarray's built-in reduction operations.

Usage::

    from earthforge.cube.stats import cube_stats

    result = await cube_stats("era5.zarr", variable="temperature", reduce_dims=["time"])
"""

from __future__ import annotations

import asyncio
from functools import partial

from pydantic import BaseModel, Field

from earthforge.cube.errors import CubeError


class CubeStatsResult(BaseModel):
    """Result of datacube statistics computation.

    Attributes:
        source: Input path.
        variable: Variable that statistics were computed for.
        reduce_dims: Dimensions that were reduced.
        remaining_dims: Dimensions remaining after reduction.
        operation: Statistical operation applied.
        min: Global minimum of the result.
        max: Global maximum of the result.
        mean: Global mean of the result.
        output: Output file path if saved.
    """

    source: str = Field(title="Source")
    variable: str = Field(title="Variable")
    reduce_dims: list[str] = Field(default_factory=list, title="Reduced Dims")
    remaining_dims: list[str] = Field(default_factory=list, title="Remaining Dims")
    operation: str = Field(title="Operation")
    min: float = Field(title="Min")
    max: float = Field(title="Max")
    mean: float = Field(title="Mean")
    output: str | None = Field(default=None, title="Output")


async def cube_stats(
    source: str,
    variable: str,
    *,
    reduce_dims: list[str] | None = None,
    operation: str = "mean",
    output: str | None = None,
) -> CubeStatsResult:
    """Compute aggregate statistics over datacube dimensions.

    Parameters:
        source: Path to a Zarr store or NetCDF file.
        variable: Name of the data variable to compute stats for.
        reduce_dims: Dimensions to reduce over. Default: all dimensions.
        operation: One of ``"mean"``, ``"min"``, ``"max"``, ``"std"``, ``"sum"``.
        output: Optional output path to save the reduced dataset.

    Returns:
        A :class:`CubeStatsResult` with computed statistics.

    Raises:
        CubeError: If the computation fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _stats_sync,
            source,
            variable,
            reduce_dims=reduce_dims,
            operation=operation,
            output=output,
        ),
    )


_OPERATIONS = {"mean", "min", "max", "std", "sum"}


def _stats_sync(
    source: str,
    variable: str,
    *,
    reduce_dims: list[str] | None = None,
    operation: str = "mean",
    output: str | None = None,
) -> CubeStatsResult:
    """Synchronous cube stats implementation."""
    try:
        import numpy as np
        import xarray as xr
    except ImportError as exc:
        raise CubeError("xarray is required for cube stats: pip install earthforge[cube]") from exc

    if operation not in _OPERATIONS:
        supported = ", ".join(sorted(_OPERATIONS))
        raise CubeError(f"Unknown operation '{operation}'. Supported: {supported}")

    try:
        if source.lower().endswith(".zarr") or __import__("pathlib").Path(source).is_dir():
            try:
                ds = xr.open_zarr(source, consolidated=True)
            except Exception:
                ds = xr.open_zarr(source, consolidated=False)
        else:
            ds = xr.open_dataset(source)
    except Exception as exc:
        raise CubeError(f"Cannot open datacube: {exc}") from exc

    if variable not in ds.data_vars:
        available = list(ds.data_vars)
        ds.close()
        raise CubeError(f"Variable '{variable}' not found. Available: {available}")

    var = ds[variable]
    all_dims = list(var.dims)
    dims_to_reduce = reduce_dims if reduce_dims else all_dims

    invalid_dims = set(dims_to_reduce) - set(all_dims)
    if invalid_dims:
        ds.close()
        raise CubeError(f"Dimensions not found: {invalid_dims}. Available: {all_dims}")

    remaining = [d for d in all_dims if d not in dims_to_reduce]

    try:
        var_loaded = var.load()
        reduced = getattr(var_loaded, operation)(dim=dims_to_reduce)
        result_values = reduced.values

        result_min = float(np.nanmin(result_values))
        result_max = float(np.nanmax(result_values))
        result_mean = float(np.nanmean(result_values))
    except Exception as exc:
        ds.close()
        raise CubeError(f"Statistics computation failed: {exc}") from exc

    output_path: str | None = None
    if output:
        from pathlib import Path

        out_p = Path(output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        try:
            result_ds = reduced.to_dataset(name=variable)
            if output.lower().endswith(".zarr"):
                result_ds.to_zarr(str(out_p), mode="w")
            else:
                result_ds.to_netcdf(str(out_p))
            output_path = str(out_p)
        except Exception as exc:
            raise CubeError(f"Failed to write output: {exc}") from exc

    ds.close()

    return CubeStatsResult(
        source=source,
        variable=variable,
        reduce_dims=dims_to_reduce,
        remaining_dims=remaining,
        operation=operation,
        min=result_min,
        max=result_max,
        mean=result_mean,
        output=output_path,
    )
