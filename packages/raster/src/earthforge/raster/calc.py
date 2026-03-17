"""Raster band math calculator.

Evaluates mathematical expressions across raster bands using the safe
expression evaluator from ``earthforge.core.expression``. Supports multi-file
inputs (one file per band variable) and produces a single-band output GeoTIFF.

Usage::

    from earthforge.raster.calc import raster_calc

    result = await raster_calc(
        expression="(B08 - B04) / (B08 + B04)",
        inputs={"B08": "nir.tif", "B04": "red.tif"},
        output="ndvi.tif",
    )
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from earthforge.core.expression import extract_variables, safe_eval
from earthforge.raster.errors import RasterError


class RasterCalcResult(BaseModel):
    """Result of a band math calculation.

    Attributes:
        expression: The expression that was evaluated.
        output: Output file path.
        width: Output raster width.
        height: Output raster height.
        dtype: Output data type.
        crs: CRS of the output.
        file_size_bytes: Size of the output file.
    """

    expression: str = Field(title="Expression")
    output: str = Field(title="Output")
    width: int = Field(title="Width")
    height: int = Field(title="Height")
    dtype: str = Field(title="Dtype")
    crs: str | None = Field(default=None, title="CRS")
    file_size_bytes: int = Field(title="File Size (bytes)")


async def raster_calc(
    expression: str,
    inputs: dict[str, str],
    output: str,
    *,
    dtype: str = "float32",
    nodata: float | None = None,
) -> RasterCalcResult:
    """Evaluate a band math expression across raster inputs.

    Parameters:
        expression: Math expression (e.g. ``"(B08 - B04) / (B08 + B04)"``).
        inputs: Mapping of variable name to file path.
        output: Output GeoTIFF path.
        dtype: Output data type (default: ``"float32"``).
        nodata: Nodata value for the output (default: None).

    Returns:
        A :class:`RasterCalcResult` with output metadata.

    Raises:
        RasterError: If inputs can't be read or expression is invalid.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(_raster_calc_sync, expression, inputs, output, dtype=dtype, nodata=nodata),
    )


def _raster_calc_sync(
    expression: str,
    inputs: dict[str, str],
    output: str,
    *,
    dtype: str = "float32",
    nodata: float | None = None,
) -> RasterCalcResult:
    """Synchronous band math implementation."""
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:
        raise RasterError(
            "rasterio and numpy are required: pip install earthforge[raster]"
        ) from exc

    # Validate expression and find needed variables
    try:
        needed = extract_variables(expression)
    except ValueError as exc:
        raise RasterError(f"Invalid expression: {exc}") from exc

    missing = needed - set(inputs.keys())
    if missing:
        raise RasterError(
            f"Expression references undefined variables: {', '.join(sorted(missing))}. "
            f"Available inputs: {', '.join(sorted(inputs.keys()))}"
        )

    # Load bands
    env: dict[str, Any] = {}
    profile_out: dict[str, Any] = {}

    try:
        for var_name, path in inputs.items():
            if var_name not in needed:
                continue
            with rasterio.open(path) as src:
                arr = src.read(1).astype(np.float64)
                env[var_name] = arr
                if not profile_out:
                    profile_out = src.profile.copy()
    except Exception as exc:
        raise RasterError(f"Failed to read input rasters: {exc}") from exc

    # Evaluate expression
    try:
        result_arr = safe_eval(expression, env)
    except ValueError as exc:
        raise RasterError(f"Expression evaluation failed: {exc}") from exc

    result_arr = np.asarray(result_arr).astype(dtype)

    # Write output
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile_out.update(
        dtype=dtype,
        count=1,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    if nodata is not None:
        profile_out["nodata"] = nodata

    try:
        with rasterio.open(str(output_path), "w", **profile_out) as dst:
            dst.write(result_arr, 1)
    except Exception as exc:
        raise RasterError(f"Failed to write output: {exc}") from exc

    crs = str(profile_out.get("crs")) if profile_out.get("crs") else None

    return RasterCalcResult(
        expression=expression,
        output=str(output_path),
        width=int(profile_out["width"]),
        height=int(profile_out["height"]),
        dtype=dtype,
        crs=crs,
        file_size_bytes=output_path.stat().st_size,
    )
