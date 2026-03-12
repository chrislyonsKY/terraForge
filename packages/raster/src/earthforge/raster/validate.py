"""COG compliance validation backed by rio-cogeo.

Delegates structural validation to ``rio-cogeo``, the community-standard
COG validation library, and supplements with rasterio-based checks for
compression and format detection.

Checks performed:

1. **geotiff** — File is a GeoTIFF (rasterio driver check).
2. **tiled** — Data is stored in tiles, not strips (rio-cogeo).
3. **overviews** — At least one overview level is present (rio-cogeo strict
   mode + rasterio fallback).
4. **ifd_order** — IFD ordering is correct: overview data precedes full-
   resolution data in the file (rio-cogeo byte-level check).
5. **compression** — Data is compressed (rasterio).

rio-cogeo is the authoritative source for checks 2-4. Its byte-level IFD
ordering check catches files that appear valid from rasterio metadata alone
but have incorrect internal structure. Using ``strict=True`` treats missing
overviews as a validation error rather than a warning.

Usage::

    from earthforge.raster.validate import validate_cog

    result = await validate_cog("/path/to/file.tif")
    assert result.is_valid
"""

from __future__ import annotations

import asyncio
from functools import partial

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError

_COG_CHECK_NAMES = ("geotiff", "tiled", "overviews", "ifd_order", "compression")


class ValidationCheck(BaseModel):
    """Result of a single validation check.

    Attributes:
        name: Check identifier (e.g. ``"tiled"``, ``"overviews"``).
        passed: Whether this check passed.
        message: Human-readable result description.
    """

    name: str = Field(title="Check")
    passed: bool = Field(title="Passed")
    message: str = Field(title="Message")


class CogValidationResult(BaseModel):
    """Structured result from COG validation.

    Attributes:
        source: The file that was validated.
        is_valid: Whether all checks passed.
        checks: Individual check results.
        summary: One-line summary of the validation.
    """

    source: str = Field(title="Source")
    is_valid: bool = Field(title="Valid COG")
    checks: list[ValidationCheck] = Field(title="Checks")
    summary: str = Field(title="Summary")


def _classify_message(msg: str) -> str:
    """Map a rio-cogeo error/warning string to a named check identifier.

    Parameters:
        msg: Error or warning message from rio-cogeo.

    Returns:
        One of the standard check names, or ``"spec_compliance"`` for
        messages that do not match a known pattern.
    """
    lower = msg.lower()
    if "not tiled" in lower:
        return "tiled"
    if "overview" in lower:
        return "overviews"
    if "ifd" in lower or "ordering" in lower:
        return "ifd_order"
    if "ghost" in lower:
        return "ghost_blocks"
    if "geotiff" in lower or "not a tiff" in lower:
        return "geotiff"
    return "spec_compliance"


def _validate_cog_sync(source: str) -> CogValidationResult:
    """Validate COG compliance synchronously using rio-cogeo.

    Parameters:
        source: Path or URL to a GeoTIFF file.

    Returns:
        Structured validation result.

    Raises:
        RasterError: If rio-cogeo is not installed, or if the file cannot
            be opened or validated.
    """
    try:
        from rio_cogeo.cogeo import cog_validate as _rio_validate  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RasterError(
            "rio-cogeo is required for COG validation: pip install earthforge[raster]"
        ) from exc

    try:
        is_rio_valid, errors, warnings = _rio_validate(source, strict=True, quiet=True)
    except Exception as exc:
        raise RasterError(f"Failed to validate '{source}': {exc}") from exc

    named: dict[str, ValidationCheck] = {}

    # rio-cogeo errors → failed checks
    for err in errors:
        name = _classify_message(err)
        named[name] = ValidationCheck(name=name, passed=False, message=err)

    # rio-cogeo warnings → informational checks (passed, with warning prefix)
    for warn in warnings:
        name = _classify_message(warn)
        if name not in named:
            named[name] = ValidationCheck(
                name=name, passed=True, message=f"Warning: {warn}"
            )

    # Supplementary rasterio checks for geotiff driver and compression.
    # rio-cogeo does not surface these as structured named checks, but they
    # are important for users to see in the output.
    try:
        import rasterio  # type: ignore[import-untyped]

        with rasterio.open(source) as ds:
            if "geotiff" not in named:
                is_gtiff = ds.driver == "GTiff"
                named["geotiff"] = ValidationCheck(
                    name="geotiff",
                    passed=is_gtiff,
                    message="File is a GeoTIFF"
                    if is_gtiff
                    else f"Not a GeoTIFF (driver={ds.driver})",
                )

            if "overviews" not in named:
                ovr_levels = ds.overviews(1) if ds.count > 0 else []
                has_ovr = len(ovr_levels) > 0
                named["overviews"] = ValidationCheck(
                    name="overviews",
                    passed=has_ovr,
                    message=f"Overviews present (levels={ovr_levels})"
                    if has_ovr
                    else "No overviews — at least one overview level is required",
                )

            if "compression" not in named:
                comp = ds.compression
                has_comp = comp is not None
                named["compression"] = ValidationCheck(
                    name="compression",
                    passed=has_comp,
                    message=f"Compressed ({comp.value})"
                    if has_comp
                    else "Uncompressed — compression is recommended for COGs",
                )
    except RasterError:
        raise
    except Exception:  # noqa: S110
        pass  # Supplementary checks are best-effort; don't mask the primary result

    # Ensure all standard named checks are present, defaulting to passed if
    # rio-cogeo raised no error or warning for them.
    for std_name in _COG_CHECK_NAMES:
        if std_name not in named:
            named[std_name] = ValidationCheck(
                name=std_name,
                passed=True,
                message=f"{std_name.replace('_', ' ').title()}: OK",
            )

    checks = list(named.values())

    # We may be stricter than rio-cogeo's bare is_valid in some areas
    # (e.g. requiring overviews even for small files). Fail if any named
    # check fails, regardless of rio-cogeo's own verdict.
    checks_pass = all(c.passed for c in checks if c.name in _COG_CHECK_NAMES)
    is_valid = is_rio_valid and checks_pass

    passed_count = sum(1 for c in checks if c.passed)
    total_count = len(checks)
    summary = (
        f"Valid COG ({passed_count}/{total_count} checks passed)"
        if is_valid
        else f"Not a valid COG ({passed_count}/{total_count} checks passed)"
    )

    return CogValidationResult(
        source=source, is_valid=is_valid, checks=checks, summary=summary
    )


async def validate_cog(source: str) -> CogValidationResult:
    """Validate COG compliance for a raster file.

    Delegates to rio-cogeo for byte-level IFD ordering and structural
    validation, which catches files that appear valid from metadata alone
    but have incorrect internal structure.

    Parameters:
        source: Path or URL to a GeoTIFF file.

    Returns:
        Structured validation result with named per-check results.

    Raises:
        RasterError: If rio-cogeo is not installed, or the file cannot
            be opened.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_validate_cog_sync, source))
