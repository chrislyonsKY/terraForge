"""XYZ/TMS static tile generation from raster files.

Generates a directory of PNG tiles in ``{z}/{x}/{y}.png`` structure from a
raster file (typically a COG). Uses windowed reads at tile boundaries and
overview levels for lower zoom levels.

Tile math is implemented inline (~40 lines) to avoid adding ``mercantile``
as a dependency.

Usage::

    from earthforge.raster.tile import generate_tiles

    result = await generate_tiles("elevation.tif", output_dir="tiles/", zoom_range=(8, 12))
"""

from __future__ import annotations

import asyncio
import logging
import math
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError

logger = logging.getLogger(__name__)


class TileResult(BaseModel):
    """Result of tile generation.

    Attributes:
        source: Input raster path.
        output_dir: Directory containing generated tiles.
        zoom_min: Minimum zoom level generated.
        zoom_max: Maximum zoom level generated.
        tile_count: Total number of tiles generated.
        tile_size: Tile size in pixels.
    """

    source: str = Field(title="Source")
    output_dir: str = Field(title="Output Dir")
    zoom_min: int = Field(title="Min Zoom")
    zoom_max: int = Field(title="Max Zoom")
    tile_count: int = Field(title="Tiles")
    tile_size: int = Field(title="Tile Size (px)")


async def generate_tiles(
    source: str,
    output_dir: str,
    *,
    zoom_range: tuple[int, int] = (0, 5),
    tile_size: int = 256,
) -> TileResult:
    """Generate XYZ tiles from a raster file.

    Parameters:
        source: Path or URL to a raster file.
        output_dir: Directory to write ``{z}/{x}/{y}.png`` tiles into.
        zoom_range: ``(min_zoom, max_zoom)`` inclusive.
        tile_size: Tile size in pixels (default: 256).

    Returns:
        A :class:`TileResult` with generation summary.

    Raises:
        RasterError: If the raster cannot be read or tiles cannot be written.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _generate_tiles_sync,
            source,
            output_dir,
            zoom_range=zoom_range,
            tile_size=tile_size,
        ),
    )


# ---------------------------------------------------------------------------
# Inline tile math (no mercantile dependency)
# ---------------------------------------------------------------------------


def _lng_lat_to_tile(lng: float, lat: float, zoom: int) -> tuple[int, int]:
    """Convert longitude/latitude to tile x, y at given zoom.

    Parameters:
        lng: Longitude in degrees.
        lat: Latitude in degrees.
        zoom: Zoom level.

    Returns:
        Tuple of (tile_x, tile_y).
    """
    n = 2**zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    x = max(0, min(x, n - 1))
    y = max(0, min(y, n - 1))
    return x, y


def _tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Get the WGS84 bounding box for a tile.

    Parameters:
        x: Tile X coordinate.
        y: Tile Y coordinate.
        zoom: Zoom level.

    Returns:
        Tuple of (west, south, east, north) in degrees.
    """
    n = 2**zoom
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    south_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    north = math.degrees(north_rad)
    south = math.degrees(south_rad)
    return west, south, east, north


def _generate_tiles_sync(
    source: str,
    output_dir: str,
    *,
    zoom_range: tuple[int, int] = (0, 5),
    tile_size: int = 256,
) -> TileResult:
    """Synchronous tile generation implementation."""
    try:
        import rasterio
        from rasterio.warp import transform_bounds
    except ImportError as exc:
        raise RasterError(
            "rasterio and numpy are required: pip install earthforge[raster]"
        ) from exc

    try:
        import PIL

        del PIL
    except ImportError as exc:
        raise RasterError("Pillow is required for tile generation: pip install Pillow") from exc

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    tile_count = 0
    zoom_min, zoom_max = zoom_range

    try:
        with rasterio.open(source) as src:
            # Get bounds in WGS84
            if src.crs and str(src.crs) != "EPSG:4326":
                bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            else:
                bounds = src.bounds

            west, south, east, north = bounds

            for zoom in range(zoom_min, zoom_max + 1):
                min_x, min_y = _lng_lat_to_tile(west, north, zoom)
                max_x, max_y = _lng_lat_to_tile(east, south, zoom)

                for tx in range(min_x, max_x + 1):
                    for ty in range(min_y, max_y + 1):
                        tile_dir = out_path / str(zoom) / str(tx)
                        tile_dir.mkdir(parents=True, exist_ok=True)
                        tile_path = tile_dir / f"{ty}.png"

                        try:
                            _render_tile(src, tx, ty, zoom, tile_size, tile_path)
                            tile_count += 1
                        except Exception:
                            logger.debug(
                                "Skipping tile z=%d x=%d y=%d (outside data)",
                                zoom,
                                tx,
                                ty,
                            )
                            continue

    except RasterError:
        raise
    except Exception as exc:
        raise RasterError(f"Tile generation failed: {exc}") from exc

    return TileResult(
        source=source,
        output_dir=str(out_path),
        zoom_min=zoom_min,
        zoom_max=zoom_max,
        tile_count=tile_count,
        tile_size=tile_size,
    )


def _render_tile(
    src: Any,
    tx: int,
    ty: int,
    zoom: int,
    tile_size: int,
    output: Path,
) -> None:
    """Render a single tile to PNG.

    Parameters:
        src: Open rasterio dataset.
        tx: Tile X coordinate.
        ty: Tile Y coordinate.
        zoom: Zoom level.
        tile_size: Output tile size in pixels.
        output: Path to write the PNG.
    """
    import numpy as np
    from PIL import Image
    from rasterio.windows import from_bounds

    tile_west, tile_south, tile_east, tile_north = _tile_bounds(tx, ty, zoom)

    # Reproject tile bounds to dataset CRS
    if src.crs and str(src.crs) != "EPSG:4326":
        from rasterio.warp import transform_bounds

        tile_bounds = transform_bounds(
            "EPSG:4326",
            src.crs,
            tile_west,
            tile_south,
            tile_east,
            tile_north,
        )
    else:
        tile_bounds = (tile_west, tile_south, tile_east, tile_north)

    window = from_bounds(*tile_bounds, transform=src.transform)

    # Read data for this window
    data = src.read(
        1,
        window=window,
        out_shape=(tile_size, tile_size),
        boundless=True,
        fill_value=0,
    )

    # Normalize to 0-255
    valid = data[data != src.nodata] if src.nodata is not None else data.ravel()
    if valid.size > 0:
        vmin, vmax = float(np.min(valid)), float(np.max(valid))
        if vmax > vmin:
            normalized = ((data - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        else:
            normalized = np.full_like(data, 128, dtype=np.uint8)
    else:
        normalized = np.zeros_like(data, dtype=np.uint8)

    img = Image.fromarray(normalized, mode="L")
    img.save(str(output), format="PNG")
