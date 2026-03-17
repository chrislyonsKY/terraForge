"""Raster statistics computation — global and zonal.

Computes summary statistics (min, max, mean, std, median, histogram) for
raster files. Supports both global statistics (entire raster) and zonal
statistics (masked to a WKT/GeoJSON geometry via ``rasterio.mask``).

Usage::

    from earthforge.raster.stats import compute_stats

    result = await compute_stats("elevation.tif")
    result = await compute_stats("elevation.tif", geometry_wkt="POLYGON(...)")
"""

from __future__ import annotations

import asyncio
from functools import partial

from pydantic import BaseModel, Field

from earthforge.raster.errors import RasterError


class BandStatistics(BaseModel):
    """Statistics for a single raster band.

    Attributes:
        band: Band index (1-based).
        min: Minimum value.
        max: Maximum value.
        mean: Mean value.
        std: Standard deviation.
        median: Median value.
        valid_pixels: Number of non-nodata pixels.
        nodata_pixels: Number of nodata pixels.
        histogram_counts: Histogram bin counts.
        histogram_edges: Histogram bin edges.
    """

    band: int = Field(title="Band")
    min: float = Field(title="Min")
    max: float = Field(title="Max")
    mean: float = Field(title="Mean")
    std: float = Field(title="Std Dev")
    median: float = Field(title="Median")
    valid_pixels: int = Field(title="Valid Pixels")
    nodata_pixels: int = Field(title="Nodata Pixels")
    histogram_counts: list[int] = Field(default_factory=list, title="Histogram Counts")
    histogram_edges: list[float] = Field(default_factory=list, title="Histogram Edges")


class RasterStatsResult(BaseModel):
    """Aggregate statistics result for a raster file.

    Attributes:
        source: Path or URL of the raster.
        width: Raster width in pixels.
        height: Raster height in pixels.
        band_count: Number of bands.
        crs: CRS string.
        is_zonal: Whether a geometry mask was applied.
        bands: Per-band statistics.
    """

    source: str = Field(title="Source")
    width: int = Field(title="Width")
    height: int = Field(title="Height")
    band_count: int = Field(title="Bands")
    crs: str | None = Field(default=None, title="CRS")
    is_zonal: bool = Field(default=False, title="Zonal")
    bands: list[BandStatistics] = Field(default_factory=list, title="Band Stats")


async def compute_stats(
    source: str,
    *,
    bands: list[int] | None = None,
    geometry_wkt: str | None = None,
    histogram_bins: int = 50,
) -> RasterStatsResult:
    """Compute raster statistics.

    Parameters:
        source: Path or URL to a raster file.
        bands: Band indices to compute (1-based). Default: all bands.
        geometry_wkt: Optional WKT geometry for zonal statistics.
        histogram_bins: Number of histogram bins (default: 50).

    Returns:
        A :class:`RasterStatsResult` with per-band statistics.

    Raises:
        RasterError: If the file cannot be opened or processed.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _compute_stats_sync,
            source,
            bands=bands,
            geometry_wkt=geometry_wkt,
            histogram_bins=histogram_bins,
        ),
    )


def _compute_stats_sync(
    source: str,
    *,
    bands: list[int] | None = None,
    geometry_wkt: str | None = None,
    histogram_bins: int = 50,
) -> RasterStatsResult:
    """Synchronous raster statistics implementation."""
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:
        raise RasterError(
            "rasterio and numpy are required: pip install earthforge[raster]"
        ) from exc

    try:
        with rasterio.open(source) as src:
            width = src.width
            height = src.height
            band_count = src.count
            crs = str(src.crs) if src.crs else None
            nodata = src.nodata

            band_indices = bands if bands else list(range(1, band_count + 1))
            is_zonal = geometry_wkt is not None

            if geometry_wkt:
                from shapely import wkt

                geom = wkt.loads(geometry_wkt)
                geom_geojson = geom.__geo_interface__
                from rasterio.mask import mask

                masked_data, _ = mask(src, [geom_geojson], crop=True, nodata=nodata)
            else:
                masked_data = None

            band_stats: list[BandStatistics] = []
            for band_idx in band_indices:
                if band_idx < 1 or band_idx > band_count:
                    raise RasterError(f"Band {band_idx} out of range (1-{band_count})")

                if masked_data is not None:
                    arr = masked_data[band_idx - 1].astype(np.float64)
                else:
                    arr = src.read(band_idx).astype(np.float64)

                if nodata is not None:
                    valid_mask = ~np.isclose(arr, nodata)
                else:
                    valid_mask = ~np.isnan(arr)

                valid = arr[valid_mask]
                valid_count = int(valid.size)
                nodata_count = int(arr.size - valid_count)

                if valid_count == 0:
                    band_stats.append(
                        BandStatistics(
                            band=band_idx,
                            min=0.0,
                            max=0.0,
                            mean=0.0,
                            std=0.0,
                            median=0.0,
                            valid_pixels=0,
                            nodata_pixels=nodata_count,
                        )
                    )
                    continue

                counts, edges = np.histogram(valid, bins=histogram_bins)
                band_stats.append(
                    BandStatistics(
                        band=band_idx,
                        min=float(np.min(valid)),
                        max=float(np.max(valid)),
                        mean=float(np.mean(valid)),
                        std=float(np.std(valid)),
                        median=float(np.median(valid)),
                        valid_pixels=valid_count,
                        nodata_pixels=nodata_count,
                        histogram_counts=[int(c) for c in counts],
                        histogram_edges=[float(e) for e in edges],
                    )
                )

    except RasterError:
        raise
    except Exception as exc:
        raise RasterError(f"Failed to compute stats for {source}: {exc}") from exc

    return RasterStatsResult(
        source=source,
        width=width,
        height=height,
        band_count=band_count,
        crs=crs,
        is_zonal=is_zonal,
        bands=band_stats,
    )
