"""EarthForge ArcGIS Pro Python Toolbox.

Add this toolbox to ArcGIS Pro:
  1. In Catalog pane, right-click Toolboxes > Add Toolbox
  2. Browse to this .pyt file
  3. Tools appear under EarthForge in the Geoprocessing pane

Requirements:
  - ArcGIS Pro 3.x with Python 3.11+
  - earthforge packages installed in the ArcGIS Pro conda env:
      pip install earthforge-core earthforge-stac earthforge-raster earthforge-vector earthforge-cube
  - Or: add the packages/*/src directories to sys.path for development

Each tool wraps an EarthForge library function and exposes it as a standard
ArcGIS geoprocessing tool with parameter validation, progress messages,
and output integration.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


class Toolbox:
    """EarthForge — Cloud-Native Geospatial Developer Toolkit.

    Tools for STAC catalog search, COG validation, raster operations,
    vector format conversion, datacube inspection, and format detection.
    """

    def __init__(self):
        self.label = "EarthForge"
        self.alias = "earthforge"
        self.tools = [
            STACSearch,
            STACValidate,
            RasterInfo,
            RasterStats,
            RasterCalc,
            COGValidate,
            VectorConvert,
            VectorValidate,
            VectorClip,
            CubeInfo,
            CubeValidate,
            CubeConvert,
            CubeStats,
            FormatDetect,
        ]


def _ensure_imports():
    """Add EarthForge source paths if running from a development checkout.

    When installed via pip, this is a no-op. When running from a dev checkout,
    adds packages/*/src to sys.path so imports resolve.
    """
    try:
        import earthforge.core.config  # noqa: F401

        return
    except ImportError:
        pass

    pyt_dir = Path(__file__).resolve().parent
    repo_root = pyt_dir.parent.parent

    for pkg in ["core", "stac", "raster", "vector", "cube", "pipeline"]:
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
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _param(name, label, datatype, direction="Input", required=True, default=None,
           multiValue=False, category=None):
    """Create an ArcGIS tool parameter with common defaults.

    Parameters:
        name: Internal parameter name.
        label: Display label in the tool dialog.
        datatype: ArcGIS parameter data type string.
        direction: 'Input' or 'Output'.
        required: Whether the parameter is required.
        default: Default value.
        multiValue: Whether the parameter accepts multiple values.
        category: Optional parameter category for grouping.

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
        multiValue=multiValue,
    )
    if default is not None:
        p.value = default
    if category is not None:
        p.category = category
    return p


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

        p0 = _param(
            "stac_api",
            "STAC API URL",
            "GPString",
            default="https://earth-search.aws.element84.com/v1",
        )
        params.append(p0)

        p1 = _param("collection", "Collection", "GPString", default="sentinel-2-l2a")
        params.append(p1)

        p2 = _param("extent", "Search Extent", "GPExtent", required=False)
        params.append(p2)

        p3 = _param(
            "date_range",
            "Date Range (YYYY-MM-DD/YYYY-MM-DD)",
            "GPString",
            required=False,
            default="2025-06-01/2025-09-30",
        )
        params.append(p3)

        p4 = _param("max_items", "Max Items", "GPLong", default=20)
        params.append(p4)

        p5 = _param(
            "max_cloud",
            "Max Cloud Cover (%)",
            "GPDouble",
            required=False,
            default=100.0,
        )
        params.append(p5)

        p6 = _param(
            "output_geojson",
            "Output Footprints (GeoJSON)",
            "DEFile",
            direction="Output",
        )
        p6.filter.list = ["geojson", "json"]
        params.append(p6)

        return params

    def isLicensed(self):
        """Allow tool to execute — no special license required."""
        return True

    def updateParameters(self, parameters):
        """Modify parameters before validation."""
        return

    def updateMessages(self, parameters):
        """Modify messages after validation."""
        return

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

        bbox = None
        if extent:
            bbox = [extent.XMin, extent.YMin, extent.XMax, extent.YMax]

        profile = EarthForgeProfile(name="arcgis", stac_api=stac_api)

        messages.addMessage(f"Searching {collection} on {stac_api}...")
        if bbox:
            messages.addMessage(f"  Bbox: {bbox}")
        if date_range:
            messages.addMessage(f"  Date range: {date_range}")

        result = _run_async(
            search_catalog(
                profile,
                collections=[collection] if collection else None,
                bbox=bbox,
                datetime_range=date_range or None,
                max_items=max_items,
            )
        )

        messages.addMessage(f"Found {result.returned} items (matched: {result.matched})")

        items = result.items
        if max_cloud < 100:
            items = [i for i in items if (i.properties.get("eo:cloud_cover") or 0) <= max_cloud]
            messages.addMessage(f"After cloud filter (<={max_cloud}%): {len(items)} items")

        features = []
        for item in items:
            if not item.bbox:
                continue
            w, s, e, n = item.bbox
            features.append(
                {
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
                }
            )

        geojson = {"type": "FeatureCollection", "features": features}
        Path(output_path).write_text(json.dumps(geojson, indent=2))

        messages.addMessage(f"Wrote {len(features)} footprints to {output_path}")

    def postExecute(self, parameters):
        """Post-execution cleanup."""
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: STAC Validate
# ─────────────────────────────────────────────────────────────────────────────


class STACValidate:
    """Validate a STAC item or collection against the specification.

    Checks required fields, extension schemas, and structural compliance
    using pystac validation.
    """

    def __init__(self):
        self.label = "STAC Validate"
        self.description = (
            "Validate a STAC item or collection JSON file against the "
            "STAC specification. Reports required fields, extension compliance, "
            "and schema validation results."
        )
        self.category = "Discovery"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "STAC JSON (file path or URL)", "GPString")
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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute STAC validation."""
        _ensure_imports()

        from earthforge.core.config import EarthForgeProfile
        from earthforge.stac.validate import validate_stac

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        profile = EarthForgeProfile(name="arcgis", storage_backend="local")
        messages.addMessage(f"Validating: {source}")

        result = _run_async(validate_stac(profile, source))

        if result.is_valid:
            messages.addMessage(f"Result: {result.summary}")
        else:
            messages.addWarningMessage(f"Result: {result.summary}")

        for check in result.checks:
            messages.addMessage(f"  {check.status} {check.check}: {check.message}")

        if output_json:
            data = json.loads(result.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote report to {output_json}")

    def postExecute(self, parameters):
        return


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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

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
        tiling = f"{info.tile_width}x{info.tile_height}"
        messages.addMessage(f"  Tiled:       {info.is_tiled} ({tiling})")
        messages.addMessage(f"  Overviews:   {info.overview_count} {info.overview_levels}")
        messages.addMessage(f"  Compression: {info.compression}")
        messages.addMessage(f"  Bounds:      {info.bounds}")

        for band in info.bands:
            messages.addMessage(f"  Band {band.index}: dtype={band.dtype} nodata={band.nodata}")

        if output_json:
            data = json.loads(info.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote metadata to {output_json}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Raster Stats
# ─────────────────────────────────────────────────────────────────────────────


class RasterStats:
    """Compute raster statistics — min, max, mean, std, median, histogram.

    Works on local files and remote COGs. Supports per-band statistics
    and optional zonal statistics using a WKT geometry mask.
    """

    def __init__(self):
        self.label = "Raster Statistics"
        self.description = (
            "Compute global or zonal statistics for raster bands: min, max, "
            "mean, standard deviation, median, and histogram."
        )
        self.category = "Raster"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Raster Source (file path or URL)", "GPString")
        params.append(p0)

        p1 = _param(
            "bands",
            "Bands (comma-separated, 1-based)",
            "GPString",
            required=False,
        )
        params.append(p1)

        p2 = _param(
            "zone_geometry",
            "Zone Geometry (WKT)",
            "GPString",
            required=False,
            category="Zonal Statistics",
        )
        params.append(p2)

        p3 = _param(
            "histogram_bins",
            "Histogram Bins",
            "GPLong",
            required=False,
            default=50,
        )
        params.append(p3)

        p4 = _param(
            "output_json",
            "Output Statistics (JSON)",
            "DEFile",
            direction="Output",
            required=False,
        )
        params.append(p4)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute raster statistics computation."""
        _ensure_imports()

        from earthforge.raster.stats import compute_stats

        source = parameters[0].valueAsText
        bands_str = parameters[1].valueAsText
        zone_wkt = parameters[2].valueAsText if parameters[2].value else None
        bins = int(parameters[3].value or 50)
        output_json = parameters[4].valueAsText if parameters[4].value else None

        band_list = None
        if bands_str:
            band_list = [int(b.strip()) for b in bands_str.split(",")]

        messages.addMessage(f"Computing statistics: {source}")
        result = _run_async(
            compute_stats(source, bands=band_list, geometry_wkt=zone_wkt, histogram_bins=bins)
        )

        messages.addMessage(f"  Size: {result.width}x{result.height}, CRS: {result.crs}")
        if result.is_zonal:
            messages.addMessage("  Mode: Zonal (geometry mask applied)")

        for band in result.bands:
            messages.addMessage(
                f"  Band {band.band}: min={band.min:.2f} max={band.max:.2f} "
                f"mean={band.mean:.2f} std={band.std:.2f} median={band.median:.2f} "
                f"({band.valid_pixels:,} valid, {band.nodata_pixels:,} nodata)"
            )

        if output_json:
            data = json.loads(result.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote statistics to {output_json}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Raster Calc
# ─────────────────────────────────────────────────────────────────────────────


class RasterCalc:
    """Band math calculator using safe expression evaluation.

    Evaluate expressions like ``(B08 - B04) / (B08 + B04)`` for NDVI
    computation. Uses a safe AST walker — no eval() or exec().
    """

    def __init__(self):
        self.label = "Raster Band Math"
        self.description = (
            "Evaluate a band math expression across raster inputs. "
            "Example: (B08 - B04) / (B08 + B04) for NDVI. "
            "Uses a safe expression parser — no arbitrary code execution."
        )
        self.category = "Raster"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param(
            "expression",
            "Expression",
            "GPString",
            default="(B08 - B04) / (B08 + B04)",
        )
        params.append(p0)

        p1 = _param(
            "inputs",
            "Input Bands (VAR=path, one per line)",
            "GPString",
            multiValue=True,
        )
        p1.filter.type = "ValueList"
        params.append(p1)

        p2 = _param("output", "Output Raster", "DEFile", direction="Output")
        params.append(p2)

        p3 = _param(
            "dtype",
            "Output Data Type",
            "GPString",
            required=False,
            default="float32",
        )
        p3.filter.type = "ValueList"
        p3.filter.list = ["float32", "float64", "int16", "uint16"]
        params.append(p3)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute band math calculation."""
        _ensure_imports()

        from earthforge.raster.calc import raster_calc

        expression = parameters[0].valueAsText
        input_strs = parameters[1].values if parameters[1].values else []
        output = parameters[2].valueAsText
        dtype = parameters[3].valueAsText or "float32"

        input_map = {}
        for inp in input_strs:
            if "=" in inp:
                var, path = inp.split("=", 1)
                input_map[var.strip()] = path.strip()

        messages.addMessage(f"Expression: {expression}")
        messages.addMessage(f"Inputs: {input_map}")
        messages.addMessage(f"Output: {output}")

        result = _run_async(
            raster_calc(expression, input_map, output, dtype=dtype)
        )

        messages.addMessage(
            f"Result: {result.width}x{result.height} {result.dtype}, "
            f"{result.file_size_bytes:,} bytes"
        )

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: COG Validate
# ─────────────────────────────────────────────────────────────────────────────


class COGValidate:
    """Validate Cloud-Optimized GeoTIFF compliance.

    Runs byte-level validation (via rio-cogeo) checking: GeoTIFF format,
    tiled layout, overviews, compression, and IFD ordering.
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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

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

    def postExecute(self, parameters):
        return


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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

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

        result = _run_async(
            convert_vector(
                source=source,
                output=output,
                compression=compression,
            )
        )

        messages.addMessage(f"  Features:  {result.feature_count}")
        messages.addMessage(f"  Geometry:  {result.geometry_type}")
        messages.addMessage(f"  CRS:       {result.crs}")
        messages.addMessage(f"  Bbox:      {result.bbox}")
        messages.addMessage(f"  File size: {result.file_size_bytes:,} bytes")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Vector Validate
# ─────────────────────────────────────────────────────────────────────────────


class VectorValidate:
    """Validate GeoParquet schema compliance.

    Checks for geo metadata key, CRS in PROJJSON format, geometry column
    presence, encoding, and bounding box metadata.
    """

    def __init__(self):
        self.label = "GeoParquet Validate"
        self.description = (
            "Validate a GeoParquet file against the GeoParquet specification. "
            "Checks geo metadata, CRS, geometry column, encoding, and bbox."
        )
        self.category = "Vector"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "GeoParquet File", "DEFile")
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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute GeoParquet validation."""
        _ensure_imports()

        from earthforge.vector.validate import validate_geoparquet

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        messages.addMessage(f"Validating: {source}")
        result = _run_async(validate_geoparquet(source))

        if result.is_valid:
            messages.addMessage(f"Result: {result.summary}")
        else:
            messages.addWarningMessage(f"Result: {result.summary}")

        for check in result.checks:
            messages.addMessage(f"  {check.status} {check.check}: {check.message}")

        if output_json:
            data = json.loads(result.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote report to {output_json}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Vector Clip
# ─────────────────────────────────────────────────────────────────────────────


class VectorClip:
    """Clip vector features to a bounding box or geometry.

    Clips features from a GeoParquet or other vector file using either
    a bounding box extent or a WKT geometry. Outputs to GeoParquet.
    """

    def __init__(self):
        self.label = "Vector Clip"
        self.description = (
            "Clip vector features to a bounding box or WKT geometry. "
            "Input can be GeoParquet, GeoJSON, or Shapefile."
        )
        self.category = "Vector"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Input Vector Dataset", "DEFile")
        params.append(p0)

        p1 = _param("output", "Output File", "DEFile", direction="Output")
        params.append(p1)

        p2 = _param("clip_extent", "Clip Extent", "GPExtent", required=False)
        params.append(p2)

        p3 = _param(
            "clip_geometry",
            "Clip Geometry (WKT)",
            "GPString",
            required=False,
            category="Advanced",
        )
        params.append(p3)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        if not parameters[2].value and not parameters[3].value:
            parameters[2].setWarningMessage("Provide either Clip Extent or Clip Geometry")

    def execute(self, parameters, messages):
        """Execute vector clipping."""
        _ensure_imports()

        from earthforge.vector.clip import clip_features

        source = parameters[0].valueAsText
        output = parameters[1].valueAsText
        extent = parameters[2].value
        clip_wkt = parameters[3].valueAsText if parameters[3].value else None

        bbox = None
        if extent:
            bbox = (extent.XMin, extent.YMin, extent.XMax, extent.YMax)

        messages.addMessage(f"Clipping: {source}")
        result = _run_async(
            clip_features(source, output, bbox=bbox, geometry_wkt=clip_wkt)
        )

        messages.addMessage(f"  Input features:  {result.features_input:,}")
        messages.addMessage(f"  Output features: {result.features_output:,}")
        messages.addMessage(f"  Clip method:     {result.clip_method}")
        messages.addMessage(f"  Output format:   {result.output_format}")
        messages.addMessage(f"  File size:       {result.file_size_bytes:,} bytes")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Cube Info
# ─────────────────────────────────────────────────────────────────────────────


class CubeInfo:
    """Inspect datacube metadata — dimensions, variables, CRS, chunks.

    Reads only metadata (consolidated Zarr metadata or NetCDF header)
    without loading data arrays.
    """

    def __init__(self):
        self.label = "Datacube Info"
        self.description = (
            "Inspect Zarr or NetCDF datacube metadata: dimensions, variables, "
            "CRS, chunk sizes, and CF-convention attributes."
        )
        self.category = "Datacube"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Zarr Store or NetCDF File", "GPString")
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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute datacube inspection."""
        _ensure_imports()

        from earthforge.cube.info import inspect_cube

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        messages.addMessage(f"Inspecting: {source}")
        info = _run_async(inspect_cube(source))

        messages.addMessage(f"  Format: {info.format}")
        messages.addMessage(f"  Dimensions: {len(info.dimensions)}")
        for dim in info.dimensions:
            messages.addMessage(f"    {dim.name}: {dim.size} ({dim.dtype})")
        messages.addMessage(f"  Variables: {len(info.variables)}")
        for var in info.variables:
            messages.addMessage(f"    {var.name}: {var.dims} ({var.dtype})")

        if output_json:
            data = json.loads(info.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote metadata to {output_json}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Cube Validate
# ─────────────────────────────────────────────────────────────────────────────


class CubeValidate:
    """Validate datacube structure — chunks, CF-convention, CRS, coordinates.

    Checks for proper chunking, CF-convention compliance, CRS presence,
    and coordinate array completeness.
    """

    def __init__(self):
        self.label = "Datacube Validate"
        self.description = (
            "Validate a Zarr or NetCDF datacube for structural compliance: "
            "chunk structure, CF-convention, CRS, and coordinate arrays."
        )
        self.category = "Datacube"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Zarr Store or NetCDF File", "GPString")
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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute datacube validation."""
        _ensure_imports()

        from earthforge.cube.validate import validate_cube

        source = parameters[0].valueAsText
        output_json = parameters[1].valueAsText if parameters[1].value else None

        messages.addMessage(f"Validating: {source}")
        result = _run_async(validate_cube(source))

        if result.is_valid:
            messages.addMessage(f"Result: {result.summary}")
        else:
            messages.addWarningMessage(f"Result: {result.summary}")

        for check in result.checks:
            messages.addMessage(f"  {check.status} {check.check}: {check.message}")

        if output_json:
            data = json.loads(result.model_dump_json())
            Path(output_json).write_text(json.dumps(data, indent=2))
            messages.addMessage(f"Wrote report to {output_json}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Cube Convert
# ─────────────────────────────────────────────────────────────────────────────


class CubeConvert:
    """Convert between NetCDF and Zarr formats with optional rechunking.

    Converts datacubes between NetCDF and Zarr formats. Supports
    rechunking to optimize chunk sizes for analysis patterns.
    """

    def __init__(self):
        self.label = "Datacube Convert"
        self.description = (
            "Convert between NetCDF and Zarr formats. Use .zarr extension "
            "for Zarr output, .nc for NetCDF. Supports rechunking."
        )
        self.category = "Datacube"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Input (Zarr or NetCDF)", "GPString")
        params.append(p0)

        p1 = _param("output", "Output Path (.zarr or .nc)", "GPString", direction="Output")
        params.append(p1)

        p2 = _param(
            "chunks",
            "Rechunk Spec (dim=size, e.g. time=10,lat=100)",
            "GPString",
            required=False,
            category="Advanced",
        )
        params.append(p2)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute datacube conversion."""
        _ensure_imports()

        from earthforge.cube.convert import convert_cube

        source = parameters[0].valueAsText
        output = parameters[1].valueAsText
        chunks_str = parameters[2].valueAsText if parameters[2].value else None

        chunk_dict = None
        if chunks_str:
            chunk_dict = {}
            for pair in chunks_str.split(","):
                k, v = pair.split("=")
                chunk_dict[k.strip()] = int(v.strip())

        messages.addMessage(f"Converting: {source} -> {output}")
        if chunk_dict:
            messages.addMessage(f"  Rechunking: {chunk_dict}")

        result = _run_async(convert_cube(source, output, chunks=chunk_dict))

        messages.addMessage(f"  Source format: {result.source_format}")
        messages.addMessage(f"  Output format: {result.output_format}")
        messages.addMessage(f"  Variables: {result.variables}")
        messages.addMessage(f"  Dimensions: {result.dimensions}")

    def postExecute(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool: Cube Stats
# ─────────────────────────────────────────────────────────────────────────────


class CubeStats:
    """Compute aggregate statistics along datacube dimensions.

    Reduces datacube variables along specified dimensions using
    operations like mean, min, max, std, or sum.
    """

    def __init__(self):
        self.label = "Datacube Statistics"
        self.description = (
            "Compute aggregate statistics (mean, min, max, std, sum) "
            "over datacube dimensions. E.g., temporal mean of temperature."
        )
        self.category = "Datacube"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define tool parameters."""
        params = []

        p0 = _param("source", "Zarr Store or NetCDF File", "GPString")
        params.append(p0)

        p1 = _param("variable", "Variable Name", "GPString")
        params.append(p1)

        p2 = _param(
            "operation",
            "Operation",
            "GPString",
            default="mean",
        )
        p2.filter.type = "ValueList"
        p2.filter.list = ["mean", "min", "max", "std", "sum"]
        params.append(p2)

        p3 = _param(
            "reduce_dims",
            "Dimensions to Reduce (comma-separated)",
            "GPString",
            required=False,
        )
        params.append(p3)

        p4 = _param(
            "output",
            "Output File (.nc or .zarr)",
            "GPString",
            direction="Output",
            required=False,
        )
        params.append(p4)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute datacube statistics."""
        _ensure_imports()

        from earthforge.cube.stats import cube_stats

        source = parameters[0].valueAsText
        variable = parameters[1].valueAsText
        operation = parameters[2].valueAsText or "mean"
        dims_str = parameters[3].valueAsText if parameters[3].value else None
        output = parameters[4].valueAsText if parameters[4].value else None

        dim_list = None
        if dims_str:
            dim_list = [d.strip() for d in dims_str.split(",")]

        messages.addMessage(f"Computing {operation} of '{variable}' from {source}")
        if dim_list:
            messages.addMessage(f"  Reducing dimensions: {dim_list}")

        result = _run_async(
            cube_stats(source, variable, reduce_dims=dim_list, operation=operation, output=output)
        )

        messages.addMessage(f"  Operation:      {result.operation}")
        messages.addMessage(f"  Reduced dims:   {result.reduce_dims}")
        messages.addMessage(f"  Remaining dims: {result.remaining_dims}")
        messages.addMessage(f"  Min: {result.min:.4f}  Max: {result.max:.4f}  Mean: {result.mean:.4f}")

        if result.output:
            messages.addMessage(f"  Saved to: {result.output}")

    def postExecute(self, parameters):
        return


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

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        """Execute format detection."""
        _ensure_imports()

        from earthforge.core.formats import detect

        source = parameters[0].valueAsText

        messages.addMessage(f"Detecting format: {source}")
        fmt = _run_async(detect(source))

        messages.addMessage(f"  Detected: {fmt}")
        parameters[1].value = str(fmt)

    def postExecute(self, parameters):
        return
