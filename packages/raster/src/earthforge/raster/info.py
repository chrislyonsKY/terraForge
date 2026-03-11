"""Raster file inspection — COG and GeoTIFF metadata extraction.

Reads raster metadata (dimensions, CRS, bands, data types, tiling, overviews)
without loading pixel data. For remote files, rasterio uses GDAL's virtual
filesystem (vsicurl) which issues HTTP range requests automatically.

Usage::

    from earthforge.raster.info import inspect_raster, inspect_raster_sync

    info = await inspect_raster("/path/to/file.tif")
    print(info.width, info.height, info.crs)
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError

logger = logging.getLogger(__name__)


class BandInfo(BaseModel):
    """Metadata for a single raster band.

    Attributes:
        index: 1-based band index.
        dtype: Data type (e.g. ``"uint8"``, ``"float32"``).
        nodata: NoData value, or ``None`` if not set.
        description: Band description, or empty string.
    """

    index: int = Field(title="Band")
    dtype: str = Field(title="Data Type")
    nodata: float | int | None = Field(default=None, title="NoData")
    description: str = Field(default="", title="Description")


class RasterInfo(BaseModel):
    """Structured metadata for a raster file.

    Attributes:
        source: The file path or URL that was inspected.
        driver: GDAL driver name (e.g. ``"GTiff"``).
        width: Raster width in pixels.
        height: Raster height in pixels.
        crs: Coordinate reference system as a string (e.g. ``"EPSG:4326"``).
        bounds: Bounding box as ``[west, south, east, north]``.
        transform: Affine transform as a 6-element list.
        band_count: Number of bands.
        bands: Per-band metadata.
        tile_width: Tile width in pixels, or ``None`` if untiled (strip layout).
        tile_height: Tile height in pixels, or ``None`` if untiled.
        is_tiled: Whether the raster uses tiled layout.
        overview_count: Number of overview levels.
        overview_levels: List of overview decimation factors.
        compression: Compression method (e.g. ``"deflate"``, ``"lzw"``), or ``None``.
        interleave: Pixel interleaving (``"band"``, ``"pixel"``), or ``None``.
    """

    source: str = Field(title="Source")
    driver: str = Field(title="Driver")
    width: int = Field(title="Width (px)")
    height: int = Field(title="Height (px)")
    crs: str | None = Field(default=None, title="CRS")
    bounds: list[float] = Field(default_factory=list, title="Bounds")
    transform: list[float] = Field(default_factory=list, title="Transform")
    band_count: int = Field(title="Bands")
    bands: list[BandInfo] = Field(default_factory=list, title="Band Info")
    tile_width: int | None = Field(default=None, title="Tile Width")
    tile_height: int | None = Field(default=None, title="Tile Height")
    is_tiled: bool = Field(default=False, title="Tiled")
    overview_count: int = Field(default=0, title="Overviews")
    overview_levels: list[int] = Field(default_factory=list, title="Overview Levels")
    compression: str | None = Field(default=None, title="Compression")
    interleave: str | None = Field(default=None, title="Interleave")


def _read_raster_info(source: str) -> RasterInfo:
    """Synchronous implementation that reads raster metadata via rasterio.

    Parameters:
        source: Local file path or URL (rasterio handles vsicurl for URLs).

    Returns:
        Structured raster metadata.

    Raises:
        RasterError: If the file cannot be opened or read.
    """
    try:
        import rasterio
    except ImportError as exc:
        raise RasterError(
            "rasterio is required for raster operations. "
            "Install it with: pip install earthforge[raster]"
        ) from exc

    try:
        with rasterio.open(source) as ds:
            # Basic dimensions
            width = ds.width
            height = ds.height
            driver = ds.driver
            band_count = ds.count

            # CRS
            crs_str: str | None = None
            if ds.crs is not None:
                crs_str = str(ds.crs)

            # Bounds as [west, south, east, north]
            b = ds.bounds
            bounds = [b.left, b.bottom, b.right, b.top]

            # Affine transform
            t = ds.transform
            transform = [t.a, t.b, t.c, t.d, t.e, t.f]

            # Per-band info
            bands: list[BandInfo] = []
            for i in range(1, band_count + 1):
                nodata_val = ds.nodata
                desc = ds.descriptions[i - 1] or ""
                bands.append(
                    BandInfo(
                        index=i,
                        dtype=str(ds.dtypes[i - 1]),
                        nodata=nodata_val,
                        description=desc,
                    )
                )

            # Tiling info from the first IFD
            profile: dict[str, Any] = ds.profile
            blockxsize = profile.get("blockxsize", 0)
            blockysize = profile.get("blockysize", 0)
            tiled = profile.get("tiled", False)
            tile_w: int | None = blockxsize if tiled else None
            tile_h: int | None = blockysize if tiled else None

            # Overviews (from band 1)
            overviews = ds.overviews(1) if band_count > 0 else []

            # Compression and interleave
            compression = profile.get("compress")
            if compression:
                compression = str(compression).lower()
            interleave = profile.get("interleave")
            if interleave:
                interleave = str(interleave).lower()

    except RasterError:
        raise
    except Exception as exc:
        raise RasterError(f"Failed to read raster metadata from {source!r}: {exc}") from exc

    return RasterInfo(
        source=source,
        driver=driver,
        width=width,
        height=height,
        crs=crs_str,
        bounds=bounds,
        transform=transform,
        band_count=band_count,
        bands=bands,
        tile_width=tile_w,
        tile_height=tile_h,
        is_tiled=tiled,
        overview_count=len(overviews),
        overview_levels=overviews,
        compression=compression,
        interleave=interleave,
    )


async def inspect_raster(source: str) -> RasterInfo:
    """Inspect a raster file and return structured metadata.

    Runs rasterio in a thread executor since GDAL I/O is blocking.

    Parameters:
        source: Local file path or URL.

    Returns:
        Structured raster metadata.

    Raises:
        RasterError: If the file cannot be opened or read.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_read_raster_info, source))


def inspect_raster_sync(source: str) -> RasterInfo:
    """Synchronous convenience wrapper for :func:`inspect_raster`.

    Parameters:
        source: Local file path or URL.

    Returns:
        Structured raster metadata.

    Raises:
        RasterError: If the file cannot be opened or read.
    """
    return _read_raster_info(source)
