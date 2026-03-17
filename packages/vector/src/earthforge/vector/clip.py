"""Vector feature clipping by bounding box or geometry.

Clips features from a GeoParquet (or other vector) file to a bounding box
or a clipping geometry using ``shapely.intersection``.

Usage::

    from earthforge.vector.clip import clip_features

    result = await clip_features("buildings.parquet", bbox=(-85.5, 37.0, -84.0, 38.5))
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from pydantic import BaseModel, Field

from earthforge.vector.errors import VectorError


class ClipResult(BaseModel):
    """Result of clipping vector features.

    Attributes:
        source: Input file path.
        output: Output file path.
        features_input: Number of features in the input.
        features_output: Number of features after clipping.
        clip_method: Either 'bbox' or 'geometry'.
        output_format: Output file format.
        file_size_bytes: Size of the output file.
    """

    source: str = Field(title="Source")
    output: str = Field(title="Output")
    features_input: int = Field(title="Input Features")
    features_output: int = Field(title="Output Features")
    clip_method: str = Field(title="Clip Method")
    output_format: str = Field(title="Format")
    file_size_bytes: int = Field(title="File Size (bytes)")


async def clip_features(
    source: str,
    output: str | None = None,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    geometry_wkt: str | None = None,
) -> ClipResult:
    """Clip features to a bounding box or geometry.

    Parameters:
        source: Path to a vector file (GeoParquet, GeoJSON, etc.).
        output: Output path. Defaults to ``<source_stem>_clipped.parquet``.
        bbox: Bounding box as (west, south, east, north).
        geometry_wkt: WKT geometry to clip to. ``bbox`` takes precedence.

    Returns:
        A :class:`ClipResult` with clipping summary.

    Raises:
        VectorError: If the file cannot be read or no clip region is specified.
    """
    if bbox is None and geometry_wkt is None:
        raise VectorError("Either bbox or geometry_wkt must be provided for clipping")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(_clip_sync, source, output, bbox=bbox, geometry_wkt=geometry_wkt),
    )


def _clip_sync(
    source: str,
    output: str | None,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    geometry_wkt: str | None = None,
) -> ClipResult:
    """Synchronous vector clipping implementation."""
    try:
        import geopandas as gpd
        from shapely.geometry import box
    except ImportError as exc:
        raise VectorError(
            "geopandas and shapely are required: pip install earthforge[vector]"
        ) from exc

    src_path = Path(source)
    if output is None:
        output = str(src_path.with_stem(src_path.stem + "_clipped").with_suffix(".parquet"))
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if source.endswith((".parquet", ".geoparquet")):
            gdf = gpd.read_parquet(source)
        else:
            gdf = gpd.read_file(source)
    except Exception as exc:
        raise VectorError(f"Failed to read vector file {source}: {exc}") from exc

    features_input = len(gdf)

    # Build clip geometry
    if bbox is not None:
        clip_geom = box(*bbox)
        clip_method = "bbox"
    else:
        from shapely import wkt
        clip_geom = wkt.loads(geometry_wkt)
        clip_method = "geometry"

    # Clip
    try:
        clipped = gpd.clip(gdf, clip_geom)
    except Exception as exc:
        raise VectorError(f"Clipping failed: {exc}") from exc

    features_output = len(clipped)

    # Write output
    out_suffix = out_path.suffix.lower()
    try:
        if out_suffix in (".parquet", ".geoparquet"):
            clipped.to_parquet(str(out_path))
            output_format = "GeoParquet"
        elif out_suffix == ".geojson":
            clipped.to_file(str(out_path), driver="GeoJSON")
            output_format = "GeoJSON"
        elif out_suffix == ".fgb":
            clipped.to_file(str(out_path), driver="FlatGeobuf")
            output_format = "FlatGeobuf"
        else:
            clipped.to_parquet(str(out_path))
            output_format = "GeoParquet"
    except Exception as exc:
        raise VectorError(f"Failed to write output: {exc}") from exc

    return ClipResult(
        source=source,
        output=str(out_path),
        features_input=features_input,
        features_output=features_output,
        clip_method=clip_method,
        output_format=output_format,
        file_size_bytes=out_path.stat().st_size,
    )
