"""GeoTIFF to Cloud-Optimized GeoTIFF (COG) conversion.

Converts plain GeoTIFF files into COG format by applying tiling, compression,
and overview generation. Uses GDAL's COG driver (via rasterio) for spec-
compliant output with proper IFD ordering.

Usage::

    from earthforge.raster.convert import convert_to_cog

    result = await convert_to_cog("input.tif", output="output.tif")
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError


class CogConvertResult(BaseModel):
    """Structured result from a COG conversion.

    Attributes:
        source: Input file path.
        output: Output COG file path.
        width: Raster width in pixels.
        height: Raster height in pixels.
        band_count: Number of bands.
        dtype: Data type of the output.
        crs: CRS identifier string.
        compression: Compression codec used.
        blocksize: Tile size used.
        overview_levels: Overview decimation levels generated.
        overview_resampling: Resampling method used for overviews.
        file_size_bytes: Output file size in bytes.
    """

    source: str = Field(title="Source")
    output: str = Field(title="Output")
    width: int = Field(title="Width")
    height: int = Field(title="Height")
    band_count: int = Field(title="Bands")
    dtype: str = Field(title="Data Type")
    crs: str | None = Field(default=None, title="CRS")
    compression: str = Field(title="Compression")
    blocksize: int = Field(title="Block Size")
    overview_levels: list[int] = Field(title="Overview Levels")
    overview_resampling: str = Field(title="Overview Resampling")
    file_size_bytes: int | None = Field(default=None, title="Size (bytes)")


def _compute_overview_levels(width: int, height: int, blocksize: int = 512) -> list[int]:
    """Compute appropriate overview levels for a raster.

    Generates powers-of-2 overview levels until the smallest overview
    dimension is roughly one tile or smaller.

    Parameters:
        width: Raster width in pixels.
        height: Raster height in pixels.
        blocksize: Tile size (default: 512).

    Returns:
        List of overview decimation factors (e.g. ``[2, 4, 8, 16]``).
    """
    levels: list[int] = []
    factor = 2
    min_dim = min(width, height)
    while min_dim // factor >= blocksize // 2:
        levels.append(factor)
        factor *= 2
    # Always include at least one level if the raster is large enough
    if not levels and min_dim > blocksize:
        levels.append(2)
    return levels


def _convert_to_cog_sync(
    source: str,
    *,
    output: str | None = None,
    compression: str = "deflate",
    blocksize: int = 512,
    resampling: str = "average",
    overview_levels: list[int] | None = None,
) -> CogConvertResult:
    """Convert a GeoTIFF to COG synchronously.

    Parameters:
        source: Path to the input GeoTIFF.
        output: Output COG path. If ``None``, appends ``_cog`` to the stem.
        compression: Compression codec (``"deflate"``, ``"lzw"``, ``"zstd"``).
        blocksize: Tile size in pixels (default: 512).
        resampling: Resampling method for overviews (default: ``"average"``).
        overview_levels: Explicit overview levels. If ``None``, auto-computed.

    Returns:
        Structured conversion result.

    Raises:
        RasterError: If the conversion fails.
    """
    try:
        import rasterio
    except ImportError as exc:
        raise RasterError(
            "rasterio is required for COG conversion: pip install earthforge[raster]"
        ) from exc

    # Read source metadata
    try:
        src_ds = rasterio.open(source)
    except Exception as exc:
        raise RasterError(f"Failed to open '{source}': {exc}") from exc

    with src_ds:
        width = src_ds.width
        height = src_ds.height
        band_count = src_ds.count
        dtype = str(src_ds.dtypes[0])
        crs_str = str(src_ds.crs) if src_ds.crs else None

    # Compute overview levels
    if overview_levels is None:
        overview_levels = _compute_overview_levels(width, height, blocksize)

    # Determine output path
    if output is None:
        src_path = Path(source)
        output = str(src_path.with_stem(f"{src_path.stem}_cog"))

    # Use GDAL's COG driver for spec-compliant output (handles tiling, IFD
    # ordering, and overview generation in a single pass)
    try:
        from osgeo import gdal
        gdal.UseExceptions()

        compression_map = {
            "deflate": "DEFLATE",
            "lzw": "LZW",
            "zstd": "ZSTD",
            "lzma": "LZMA",
            "none": "NONE",
        }
        gdal_compress = compression_map.get(compression.lower(), compression.upper())

        resampling_map = {
            "nearest": "NEAREST",
            "bilinear": "BILINEAR",
            "cubic": "CUBIC",
            "average": "AVERAGE",
            "lanczos": "LANCZOS",
        }
        gdal_resamp = resampling_map.get(resampling.lower(), "NEAREST")

        # PREDICTOR=2 (horizontal differencing) improves DEFLATE/LZW compression
        # by 30-40% for integer/byte imagery — standard COG best practice.
        # Only applies to lossless codecs; skipped for NONE/ZSTD to avoid
        # GDAL warnings on unsupported codec+predictor combinations.
        predictor_codecs = {"DEFLATE", "LZW", "LZMA"}
        creation_options = [
            f"COMPRESS={gdal_compress}",
            f"BLOCKSIZE={blocksize}",
            f"OVERVIEW_RESAMPLING={gdal_resamp}",
        ]
        if gdal_compress in predictor_codecs:
            creation_options.append("PREDICTOR=2")

        translate_options = gdal.TranslateOptions(
            format="COG",
            creationOptions=creation_options,
        )

        result_ds = gdal.Translate(output, source, options=translate_options)
        if result_ds is None:
            raise RasterError("GDAL Translate returned None")
        result_ds = None  # Close / flush

    except ImportError as exc:
        raise RasterError(
            "GDAL is required for COG conversion: install GDAL Python bindings"
        ) from exc
    except RasterError:
        raise
    except Exception as exc:
        raise RasterError(f"COG conversion failed: {exc}") from exc

    # Read actual overview levels from the output
    with rasterio.open(output) as out_ds:
        overview_levels = out_ds.overviews(1) if out_ds.count > 0 else []

    # Get output file size
    file_size: int | None = None
    try:
        file_size = Path(output).stat().st_size
    except OSError:
        pass

    return CogConvertResult(
        source=source,
        output=output,
        width=width,
        height=height,
        band_count=band_count,
        dtype=dtype,
        crs=crs_str,
        compression=compression,
        blocksize=blocksize,
        overview_levels=overview_levels,
        overview_resampling=resampling,
        file_size_bytes=file_size,
    )


async def convert_to_cog(
    source: str,
    *,
    output: str | None = None,
    compression: str = "deflate",
    blocksize: int = 512,
    resampling: str = "average",
    overview_levels: list[int] | None = None,
) -> CogConvertResult:
    """Convert a GeoTIFF to Cloud-Optimized GeoTIFF (COG).

    Applies tiling, compression, and overview generation. The output follows
    the COG specification with proper IFD ordering (overviews after main image).

    Parameters:
        source: Path to the input GeoTIFF.
        output: Output COG path. If ``None``, appends ``_cog`` to the stem.
        compression: Compression codec (default: ``"deflate"``).
        blocksize: Tile size in pixels (default: 512).
        resampling: Resampling for overviews (default: ``"nearest"``).
        overview_levels: Explicit overview levels. ``None`` auto-computes.

    Returns:
        Structured conversion result.

    Raises:
        RasterError: If the conversion fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _convert_to_cog_sync,
            source,
            output=output,
            compression=compression,
            blocksize=blocksize,
            resampling=resampling,
            overview_levels=overview_levels,
        ),
    )
