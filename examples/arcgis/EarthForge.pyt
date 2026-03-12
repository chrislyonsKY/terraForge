"""EarthForge ArcGIS Pro Python Toolbox.

Add this toolbox to ArcGIS Pro:
  1. In Catalog pane, right-click Toolboxes > Add Toolbox
  2. Browse to this .pyt file
  3. Tools appear under EarthForge in the Geoprocessing pane

Requirements:
  - ArcGIS Pro 3.x with Python 3.11+
  - earthforge packages installed in the ArcGIS Pro conda env:
      pip install earthforge-core earthforge-stac earthforge-raster earthforge-vector
  - Or: add the packages/*/src directories to sys.path for development

Each tool wraps an EarthForge library function and exposes it as a standard
ArcGIS geoprocessing tool with parameter validation, progress messages,
and output integration.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


class Toolbox:
    """EarthForge — Cloud-Native Geospatial Developer Toolkit.

    Tools for STAC catalog search, COG validation, raster inspection,
    vector format conversion, and geospatial format detection.
    """

    def __init__(self):
        self.label = "EarthForge"
        self.alias = "earthforge"
        self.tools = [
            STACSearch,
            RasterInfo,
            COGValidate,
            VectorConvert,
            FormatDetect,
        ]


def _ensure_imports():
    """Add EarthForge source paths if running from a development checkout.

    When installed via pip, this is a no-op. When running from a dev checkout,
    adds packages/*/src to sys.path so imports resolve.
    """
    # Try importing first — if it works, we're installed
    try:
        import earthforge.core.config  # noqa: F401
        return
    except ImportError:
        pass

    # Look for dev checkout relative to this .pyt file
    pyt_dir = Path(__file__).resolve().parent
    repo_root = pyt_dir.parent  # examples/arcgis -> repo root

    for pkg in ["core", "stac", "raster", "vector"]:
        src = repo_root / "packages" / pkg / "src"
        if src.exists() and str(src) not in sys.path:
            sys.path.insert(0, str(src))


def _run_async(coro):
    """Run an async coroutine from synchronous ArcGIS Pro context.

    ArcGIS Pro's geoprocessing framework is synchronous, but EarthForge's
    library layer is async-first. This helper bridges the gap.

    Parameters:
        coro: Awaitable coroutine to execute.

    Returns:
        The coroutine's return value.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Jupyter/Pro notebook context — use nest_asyncio if available
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: STAC Search
# ─────────────────────────────────────────────────────────────────────────────

class STACSearch:
    """Search a STAC catalog for geospatial assets.

    Queries a STAC API (e.g., Element84 Earth Search) by collection,
    bounding box, and date range. Returns results as a GeoJSON file
    of scene footprints that can be added to the map.
    """

    def __init__(self):
        self.label = "STAC Search"
        self.description = (
            "Search a STAC catalog for satellite imagery, DEMs, or other "
            "geospatial assets. Returns scene footprints as GeoJSON."
        )
        self.category = "Discovery"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        # STAC API URL
        p0 = _param(
            "stac_api",
            "STAC API URL",
            "GPString",
            default="https://earth-search.aws.element84.com/v1",
        )
        params.append(p0)

        # Collection
        p1 = _param("collection", "Collection", "GPString", default="sentinel-2-l2a")
        params.append(p1)

        # Bounding box (as extent)
        p2 = _param("extent", "Search Extent", "GPExtent", required=False)
        params.append(p2)

        # Date range
        p3 = _param(
            "date_range",
            "Date Range (YYYY-MM-DD/YYYY-MM-DD)",
            "GPString",
            required=False,
            default="2025-06-01/2025-09-30",
        )
        params.append(p3)

        # Max items
        p4 = _param("max_items", "Max Items", "GPLong", default=20)
        params.append(p4)

        # Max cloud cover
        p5 = _param(
            "max_cloud",
            "Max Cloud Cover (%)",
            "GPDouble",
            required=False,
            default=100.0,
        )
        params.append(p5)

        # Output GeoJSON
        p6 = _param(
            "output_geojson",
            "Output Footprints (GeoJSON)",
            "DEFile",
            direction="Output",
        )
        p6.filter.list = ["geojson", "json"]
        params.append(p6)

        return params

    def execute(self, parameters, messages):
        """Execute STAC search and write results as GeoJSON."""
        _ensure_imports()

        from earthforge.core.config import EarthForgeProfile
        from earthforge.stac.search import search_catalog

        stac_api = parameters[0].valueAsText
        collection = parameters[1].valueAsText
        extent = parameters[2].value
        date_range = parameters[3].valueAsText
        max_items = int(parameters[4].value or 20)
        max_cloud = float(parameters[5].value) if parameters[5].value else 100.0
        output_path = parameters[6].valueAsText

        # Build bbox from ArcGIS extent
        bbox = None
        if extent:
            bbox = [extent.XMin, extent.YMin, extent.XMax, extent.YMax]

        profile = EarthForgeProfile(name="arcgis", stac_api=stac_api)

        messages.addMessage(f"Searching {collection} on {stac_api}...")
        if bbox:
            messages.addMessage(f"  Bbox: {bbox}")
        if date_range:
            messages.addMessage(f"  Date range: {date_range}")

        result = _run_async(search_catalog(
            profile,
            collections=[collection] if collection else None,
            bbox=bbox,
            datetime_range=date_range or None,
            max_items=max_items,
        ))

        messages.addMessage(f"Found {result.returned} items (matched: {result.matched})")

        # Filter by cloud cover
        items = result.items
        if max_cloud < 100:
            items = [
                i for i in items
                if (i.properties.get("eo:cloud_cover") or 0) <= max_cloud
            ]
            messages.addMessage(f"After cloud filter (<={max_cloud}%): {len(items)} items")

        # Build GeoJSON
        features = []
        for item in items:
            if not item.bbox:
                continue
            w, s, e, n = item.bbox
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
                },
                "properties": {
                    "id": item.id,
                    "collection": item.collection,
                    "datetime": item.datetime,
                    "cloud_cover": item.properties.get("eo:cloud_cover"),
                    "platform": item.properties.get("platform"),
                    "asset_count": item.asset_count,
                    "self_link": item.self_link,
                },
            })

        geojson = {"type": "FeatureCollection", "features": features}
        Path(output_path).write_text(json.dumps(geojson, indent=2))

        messages.addMessage(f"Wrote {len(features)} footprints to {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Raster Info
# ─────────────────────────────────────────────────────────────────────────────

class RasterInfo:
    """Inspect raster metadata without downloading the full file.

    Reads COG headers via HTTP range requests — for a 1 GB Sentinel-2 scene,
    this transfers ~8 KB instead of 1 GB. Works on local files and remote URLs.
    """

    def __init__(self):
        self.label = "Raster Info"
        self.description = (
            "Read raster metadata (dimensions, CRS, bands, tiling, overviews) "
            "from a local file or remote COG URL via range requests."
        )
        self.category = "Raster"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Raster Source (file path or URL)", "GPString")
        params.append(p0)

        p1 = _param(
            "output_json",
            "Output Metadata (JSON)",
            "DEFile",
            direction="Output",
            required=False,
        )
        params.append(p1)

        return params

    def execute(self, parameters, messages):
        """Execute raster inspection."""
        _ensure_imports()

        from earthforge.raster.info import inspect_raster

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        messages.addMessage(f"Inspecting: {source}")
        info = _run_async(inspect_raster(source))

        messages.addMessage(f"  Driver:      {info.driver}")
        messages.addMessage(f"  Dimensions:  {info.width} x {info.height}")
        messages.addMessage(f"  CRS:         {info.crs}")
        messages.addMessage(f"  Bands:       {info.band_count}")
        messages.addMessage(f"  Tiled:       {info.is_tiled} ({info.tile_width}x{info.tile_height})")
        messages.addMessage(f"  Overviews:   {info.overview_count} {info.overview_levels}")
        messages.addMessage(f"  Compression: {info.compression}")
        messages.addMessage(f"  Bounds:      {info.bounds}")

        for band in info.bands:
            messages.addMessage(f"  Band {band.index}: dtype={band.dtype} nodata={band.nodata}")

        if output_json:
            data = json.loads(info.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote metadata to {output_json}")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: COG Validate
# ─────────────────────────────────────────────────────────────────────────────

class COGValidate:
    """Validate Cloud-Optimized GeoTIFF compliance.

    Runs byte-level validation (via rio-cogeo) checking: GeoTIFF format,
    tiled layout, overviews, compression, and IFD ordering. Works on
    local files and remote URLs.
    """

    def __init__(self):
        self.label = "COG Validate"
        self.description = (
            "Validate that a GeoTIFF is a compliant Cloud-Optimized GeoTIFF. "
            "Checks tiling, overviews, compression, and IFD byte ordering."
        )
        self.category = "Raster"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Raster Source (file path or URL)", "GPString")
        params.append(p0)

        p1 = _param(
            "output_json",
            "Output Report (JSON)",
            "DEFile",
            direction="Output",
            required=False,
        )
        params.append(p1)

        return params

    def execute(self, parameters, messages):
        """Execute COG validation."""
        _ensure_imports()

        from earthforge.raster.validate import validate_cog

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        messages.addMessage(f"Validating: {source}")
        result = _run_async(validate_cog(source))

        status = "VALID" if result.is_valid else "INVALID"
        if result.is_valid:
            messages.addMessage(f"Result: {status}")
        else:
            messages.addWarningMessage(f"Result: {status}")

        for check in result.checks:
            tag = "PASS" if check.passed else "FAIL"
            msg = f"  [{tag}] {check.name}: {check.message}"
            if check.passed:
                messages.addMessage(msg)
            else:
                messages.addWarningMessage(msg)

        if output_json:
            data = json.loads(result.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote report to {output_json}")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Vector Convert
# ─────────────────────────────────────────────────────────────────────────────

class VectorConvert:
    """Convert vector data to GeoParquet.

    Converts Shapefile, GeoJSON, or other OGR-supported formats to GeoParquet
    with proper geo metadata (CRS, geometry types, bbox covering columns).
    """

    def __init__(self):
        self.label = "Vector Convert to GeoParquet"
        self.description = (
            "Convert Shapefile, GeoJSON, or other vector formats to GeoParquet 1.1 "
            "with proper metadata and bbox covering columns for spatial queries."
        )
        self.category = "Vector"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Input Vector Dataset", "DEFile")
        params.append(p0)

        p1 = _param("output", "Output GeoParquet", "DEFile", direction="Output")
        p1.filter.list = ["parquet"]
        params.append(p1)

        p2 = _param(
            "compression",
            "Compression",
            "GPString",
            default="snappy",
            required=False,
        )
        p2.filter.type = "ValueList"
        p2.filter.list = ["snappy", "gzip", "zstd", "none"]
        params.append(p2)

        return params

    def execute(self, parameters, messages):
        """Execute vector conversion."""
        _ensure_imports()

        from earthforge.vector.convert import convert_vector

        source = parameters[0].valueAsText
        output = parameters[1].valueAsText
        compression = parameters[2].valueAsText or "snappy"

        messages.addMessage(f"Converting: {source}")
        messages.addMessage(f"  Output: {output}")
        messages.addMessage(f"  Compression: {compression}")

        result = _run_async(convert_vector(
            source=source,
            output=output,
            compression=compression,
        ))

        messages.addMessage(f"  Features:  {result.feature_count}")
        messages.addMessage(f"  Geometry:  {result.geometry_type}")
        messages.addMessage(f"  CRS:       {result.crs}")
        messages.addMessage(f"  Bbox:      {result.bbox}")
        messages.addMessage(f"  File size: {result.file_size_bytes:,} bytes")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Format Detect
# ─────────────────────────────────────────────────────────────────────────────

class FormatDetect:
    """Detect geospatial file format.

    Uses a three-stage chain (magic bytes, extension, content inspection)
    to identify COG, GeoTIFF, GeoParquet, Parquet, FlatGeobuf, Zarr,
    NetCDF, COPC, STAC, and GeoJSON formats.
    """

    def __init__(self):
        self.label = "Format Detect"
        self.description = (
            "Identify the format of a geospatial file or URL using magic bytes, "
            "extension, and content inspection."
        )
        self.category = "Discovery"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "File Path or URL", "GPString")
        params.append(p0)

        p1 = _param(
            "detected_format",
            "Detected Format",
            "GPString",
            direction="Output",
        )
        params.append(p1)

        return params

    def execute(self, parameters, messages):
        """Execute format detection."""
        _ensure_imports()

        from earthforge.core.formats import detect

        source = parameters[0].valueAsText

        messages.addMessage(f"Detecting format: {source}")
        fmt = _run_async(detect(source))

        messages.addMessage(f"  Detected: {fmt}")
        parameters[1].value = str(fmt)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _param(name, label, datatype, direction="Input", required=True, default=None):
    """Create an ArcGIS tool parameter with common defaults.

    Parameters:
        name: Internal parameter name.
        label: Display label in the tool dialog.
        datatype: ArcGIS parameter data type string.
        direction: 'Input' or 'Output'.
        required: Whether the parameter is required.
        default: Default value.

    Returns:
        arcpy.Parameter instance.
    """
    import arcpy

    p = arcpy.Parameter(
        displayName=label,
        name=name,
        datatype=datatype,
        parameterType="Required" if required else "Optional",
        direction=direction,
    )
    if default is not None:
        p.value = default
    return p
