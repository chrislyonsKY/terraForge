"""Zarr and NetCDF datacube structure validation.

Validates datacube files against common conventions and best practices:

- Chunk structure (present and reasonable sizes)
- CF-convention compliance (units, standard_name, long_name)
- CRS presence (grid_mapping or crs_wkt attribute)
- Coordinate arrays (time, latitude/longitude or x/y)
- Dimension completeness

Usage::

    from earthforge.cube.validate import validate_cube

    result = await validate_cube("era5.zarr")
"""

from __future__ import annotations

import asyncio
from functools import partial

from pydantic import BaseModel, Field

from earthforge.core.output import StatusMarker, format_status
from earthforge.cube.errors import CubeError


class CubeValidationCheck(BaseModel):
    """Result of a single validation check.

    Attributes:
        check: Name of the validation check.
        status: Pass/fail/warn status with text marker.
        message: Human-readable detail.
    """

    check: str = Field(title="Check")
    status: str = Field(title="Status")
    message: str = Field(title="Message")


class CubeValidationResult(BaseModel):
    """Aggregate result of validating a datacube.

    Attributes:
        source: Path or URL that was validated.
        format: Detected format (zarr or netcdf).
        is_valid: Overall pass/fail.
        dimensions: List of dimension names.
        variables: List of data variable names.
        checks: Individual check results.
        summary: Human-readable one-line summary.
    """

    source: str = Field(title="Source")
    format: str = Field(title="Format")
    is_valid: bool = Field(title="Valid")
    dimensions: list[str] = Field(default_factory=list, title="Dimensions")
    variables: list[str] = Field(default_factory=list, title="Variables")
    checks: list[CubeValidationCheck] = Field(default_factory=list, title="Checks")
    summary: str = Field(title="Summary")


async def validate_cube(source: str) -> CubeValidationResult:
    """Validate a Zarr store or NetCDF file for datacube compliance.

    Parameters:
        source: Path or URL to a Zarr store or NetCDF file.

    Returns:
        A :class:`CubeValidationResult` with detailed check results.

    Raises:
        CubeError: If the file cannot be opened.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_validate_sync, source))


def _validate_sync(source: str) -> CubeValidationResult:
    """Synchronous datacube validation implementation.

    Parameters:
        source: Path to a Zarr store or NetCDF file.

    Returns:
        Validation result.
    """
    try:
        import xarray as xr
    except ImportError as exc:
        raise CubeError(
            "xarray is required for cube validation: pip install earthforge[cube]"
        ) from exc

    checks: list[CubeValidationCheck] = []

    # --- Detect format and open ---
    fmt = _detect_format(source)

    try:
        if fmt == "zarr":
            ds = xr.open_zarr(source, consolidated=True)
        else:
            ds = xr.open_dataset(source)
    except Exception:
        # Try unconsolidated Zarr
        try:
            ds = xr.open_zarr(source, consolidated=False)
            fmt = "zarr"
        except Exception as exc2:
            raise CubeError(f"Cannot open datacube at {source}: {exc2}") from exc2

    checks.append(
        CubeValidationCheck(
            check="readable",
            status=format_status(StatusMarker.PASS),
            message=f"Opened as {fmt.upper()}",
        )
    )

    dims = list(ds.dims)
    variables = list(ds.data_vars)

    # --- Dimensions check ---
    if dims:
        checks.append(
            CubeValidationCheck(
                check="dimensions",
                status=format_status(StatusMarker.PASS),
                message=f"Dimensions: {', '.join(dims)} ({len(dims)} total)",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="dimensions",
                status=format_status(StatusMarker.FAIL),
                message="No dimensions found",
            )
        )

    # --- Variables check ---
    if variables:
        checks.append(
            CubeValidationCheck(
                check="variables",
                status=format_status(StatusMarker.PASS),
                message=f"Data variables: {len(variables)}",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="variables",
                status=format_status(StatusMarker.WARN),
                message="No data variables found",
            )
        )

    # --- Coordinate arrays check ---
    coords = list(ds.coords)
    spatial_coords = {"latitude", "longitude", "lat", "lon", "x", "y"}
    has_spatial = bool(spatial_coords & set(c.lower() for c in coords))
    time_coords = {"time", "t"}
    has_time = bool(time_coords & set(c.lower() for c in coords))

    if has_spatial:
        checks.append(
            CubeValidationCheck(
                check="spatial_coords",
                status=format_status(StatusMarker.PASS),
                message="Spatial coordinate arrays found",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="spatial_coords",
                status=format_status(StatusMarker.WARN),
                message="No recognized spatial coordinates (lat/lon, x/y)",
            )
        )

    if has_time:
        checks.append(
            CubeValidationCheck(
                check="time_coord",
                status=format_status(StatusMarker.PASS),
                message="Time coordinate found",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="time_coord",
                status=format_status(StatusMarker.INFO),
                message="No time coordinate (may be a static dataset)",
            )
        )

    # --- Chunk structure ---
    chunked_vars = []
    unchunked_vars = []
    for var_name in variables:
        var = ds[var_name]
        if var.chunks is not None:
            chunked_vars.append(var_name)
        else:
            unchunked_vars.append(var_name)

    if chunked_vars:
        checks.append(
            CubeValidationCheck(
                check="chunks",
                status=format_status(StatusMarker.PASS),
                message=f"{len(chunked_vars)} variable(s) are chunked",
            )
        )
    elif fmt == "zarr":
        checks.append(
            CubeValidationCheck(
                check="chunks",
                status=format_status(StatusMarker.WARN),
                message="Zarr store has no chunked variables",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="chunks",
                status=format_status(StatusMarker.INFO),
                message="NetCDF file (chunking optional)",
            )
        )

    # --- CF-convention checks ---
    cf_pass = 0
    cf_warn = 0
    for var_name in variables:
        var = ds[var_name]
        attrs = var.attrs
        has_units = "units" in attrs
        has_long = "long_name" in attrs or "standard_name" in attrs

        if has_units and has_long:
            cf_pass += 1
        elif has_units or has_long:
            cf_warn += 1

    if cf_pass == len(variables) and variables:
        checks.append(
            CubeValidationCheck(
                check="cf_convention",
                status=format_status(StatusMarker.PASS),
                message="All variables have CF-convention attributes (units + name)",
            )
        )
    elif cf_pass + cf_warn > 0:
        checks.append(
            CubeValidationCheck(
                check="cf_convention",
                status=format_status(StatusMarker.WARN),
                message=f"Partial CF-convention compliance: {cf_pass} full, {cf_warn} partial, "
                f"{len(variables) - cf_pass - cf_warn} missing",
            )
        )
    elif variables:
        checks.append(
            CubeValidationCheck(
                check="cf_convention",
                status=format_status(StatusMarker.WARN),
                message="No CF-convention attributes found on variables",
            )
        )

    # --- CRS check ---
    has_crs = False
    crs_source = ""

    # Check for grid_mapping attribute
    for var_name in variables:
        gm = ds[var_name].attrs.get("grid_mapping")
        if gm and gm in ds:
            has_crs = True
            crs_source = f"grid_mapping '{gm}'"
            break

    # Check for crs_wkt in global attrs
    if not has_crs:
        for attr in ("crs_wkt", "spatial_ref", "crs"):
            if attr in ds.attrs:
                has_crs = True
                crs_source = f"global attribute '{attr}'"
                break

    # Check coord vars
    if not has_crs:
        for coord_name in coords:
            coord = ds.coords[coord_name]
            if "crs_wkt" in coord.attrs or "spatial_ref" in coord.attrs:
                has_crs = True
                crs_source = f"coordinate '{coord_name}' attributes"
                break

    if has_crs:
        checks.append(
            CubeValidationCheck(
                check="crs",
                status=format_status(StatusMarker.PASS),
                message=f"CRS found via {crs_source}",
            )
        )
    else:
        checks.append(
            CubeValidationCheck(
                check="crs",
                status=format_status(StatusMarker.WARN),
                message="No CRS found (check grid_mapping or crs_wkt attributes)",
            )
        )

    ds.close()

    # --- Summary ---
    fail_count = sum(1 for c in checks if StatusMarker.FAIL.value in c.status)
    warn_count = sum(1 for c in checks if StatusMarker.WARN.value in c.status)
    pass_count = sum(1 for c in checks if StatusMarker.PASS.value in c.status)
    is_valid = fail_count == 0

    if is_valid:
        summary = format_status(
            StatusMarker.PASS,
            f"Valid {fmt.upper()} datacube ({pass_count} checks passed"
            + (f", {warn_count} warning(s)" if warn_count else "")
            + ")",
        )
    else:
        summary = format_status(
            StatusMarker.FAIL,
            f"Invalid datacube ({fail_count} failure(s), {warn_count} warning(s))",
        )

    return CubeValidationResult(
        source=source,
        format=fmt,
        is_valid=is_valid,
        dimensions=dims,
        variables=variables,
        checks=checks,
        summary=summary,
    )


def _detect_format(source: str) -> str:
    """Detect if the source is a Zarr store or NetCDF file.

    Parameters:
        source: Path or URL.

    Returns:
        ``"zarr"`` or ``"netcdf"``.
    """
    source_lower = source.lower()
    if source_lower.endswith(".zarr") or source_lower.endswith("/.zmetadata"):
        return "zarr"
    if source_lower.endswith((".nc", ".nc4", ".netcdf", ".hdf5", ".h5")):
        return "netcdf"
    # Default: try zarr first (directory-based)
    from pathlib import Path as PathLib

    p = PathLib(source)
    if p.is_dir():
        return "zarr"
    return "netcdf"
