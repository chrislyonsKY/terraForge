"""Raster preview generation.

Generates PNG quicklook images from raster files by reading overview levels
(or downsampling) to avoid loading the full resolution dataset. For remote
COGs, this means only the overview bytes are fetched — not the full file.

Usage::

    from earthforge.raster.preview import generate_preview

    result = await generate_preview("s3://bucket/image.tif", max_size=512)
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError


class PreviewResult(BaseModel):
    """Structured result from preview generation.

    Attributes:
        source: The raster file that was previewed.
        output_path: Path to the generated PNG file.
        width: Preview image width in pixels.
        height: Preview image height in pixels.
        bands_used: Number of bands rendered.
        overview_level: Overview level used (``None`` if full resolution was downsampled).
    """

    source: str = Field(title="Source")
    output_path: str = Field(title="Output")
    width: int = Field(title="Width")
    height: int = Field(title="Height")
    bands_used: int = Field(title="Bands")
    overview_level: int | None = Field(default=None, title="Overview Level")


def _generate_preview_sync(
    source: str,
    output_path: str | None,
    max_size: int,
) -> PreviewResult:
    """Generate a PNG preview synchronously.

    Parameters:
        source: Path or URL to a raster file.
        output_path: Output PNG path. If ``None``, derives from source filename.
        max_size: Maximum dimension (width or height) in pixels.

    Returns:
        Structured preview result.

    Raises:
        RasterError: If the file cannot be read or preview cannot be generated.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
    except ImportError as exc:
        raise RasterError(
            "rasterio and numpy are required for preview: pip install earthforge[raster]"
        ) from exc

    try:
        ds = rasterio.open(source)
    except Exception as exc:
        raise RasterError(f"Failed to open raster file '{source}': {exc}") from exc

    with ds:
        # Determine output size
        aspect = ds.width / ds.height
        if ds.width >= ds.height:
            out_w = min(max_size, ds.width)
            out_h = max(1, int(out_w / aspect))
        else:
            out_h = min(max_size, ds.height)
            out_w = max(1, int(out_h * aspect))

        # Determine which overview level to use
        overview_level: int | None = None
        if ds.overviews(1):
            overviews = ds.overviews(1)
            # Find the smallest overview that's still >= our target size
            for ovr in sorted(overviews):
                if ds.width // ovr >= out_w:
                    overview_level = ovr
                    break
            if overview_level is None:
                overview_level = overviews[-1] if overviews else None

        # Select bands for rendering (RGB if 3+ bands, single band otherwise)
        band_count = ds.count
        if band_count >= 3:
            bands_to_read = [1, 2, 3]
        else:
            bands_to_read = [1]

        # Read at reduced resolution
        data = ds.read(
            bands_to_read,
            out_shape=(len(bands_to_read), out_h, out_w),
            resampling=Resampling.bilinear,
        )

        # Normalize to uint8 for PNG output
        data_float = data.astype(np.float64)
        for i in range(data_float.shape[0]):
            band = data_float[i]
            vmin = np.nanpercentile(band[band != ds.nodata] if ds.nodata is not None else band, 2)
            vmax = np.nanpercentile(band[band != ds.nodata] if ds.nodata is not None else band, 98)
            if vmax > vmin:
                data_float[i] = np.clip((band - vmin) / (vmax - vmin) * 255, 0, 255)
            else:
                data_float[i] = 0
        data_uint8 = data_float.astype(np.uint8)

    # Determine output path
    if output_path is None:
        is_remote = source.startswith(("http://", "https://"))
        src_stem = "preview" if is_remote else Path(source).stem
        output_path = f"{src_stem}_preview.png"

    # Write PNG using rasterio
    try:
        with rasterio.open(
            output_path,
            "w",
            driver="PNG",
            width=out_w,
            height=out_h,
            count=len(bands_to_read),
            dtype="uint8",
        ) as out_ds:
            out_ds.write(data_uint8)
    except Exception as exc:
        raise RasterError(f"Failed to write preview to '{output_path}': {exc}") from exc

    return PreviewResult(
        source=source,
        output_path=output_path,
        width=out_w,
        height=out_h,
        bands_used=len(bands_to_read),
        overview_level=overview_level,
    )


async def generate_preview(
    source: str,
    *,
    output_path: str | None = None,
    max_size: int = 512,
) -> PreviewResult:
    """Generate a PNG quicklook from a raster file.

    Reads overview levels when available to minimize data transfer for remote
    files. For local files, downsamples at read time.

    Parameters:
        source: Path or URL to a raster file.
        output_path: Output PNG path. If ``None``, derives from source filename.
        max_size: Maximum dimension in pixels (default: 512).

    Returns:
        Structured preview result.

    Raises:
        RasterError: If the file cannot be read or preview cannot be generated.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, partial(_generate_preview_sync, source, output_path, max_size)
    )
