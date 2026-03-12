"""EarthForge centralized format detection.

Identifies geospatial file formats using a three-stage detection chain:

1. **Magic bytes** — Read the first 512 bytes and match known signatures.
2. **File extension** — Fall back to extension-based lookup.
3. **Content inspection** — For ambiguous cases (e.g. GeoTIFF vs COG),
   perform format-specific structural checks.

Domain packages can register additional content inspectors via
:func:`register_inspector` to extend detection without modifying this module.

The detection chain works on both local paths and remote URLs. For remote
files, only the first 512 bytes are fetched via HTTP range request — no
full downloads.

Usage::

    from earthforge.core.formats import detect, detect_sync, FormatType

    fmt = await detect("/path/to/file.tif")
    assert fmt == FormatType.GEOTIFF
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from earthforge.core.errors import FormatDetectionError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile

logger = logging.getLogger(__name__)


class FormatType(StrEnum):
    """Known geospatial file format identifiers.

    Members map to canonical format names used throughout EarthForge for
    dispatch, validation, and output labeling.
    """

    COG = "cog"
    GEOTIFF = "geotiff"
    GEOPARQUET = "geoparquet"
    PARQUET = "parquet"
    FLATGEOBUF = "flatgeobuf"
    ZARR = "zarr"
    NETCDF = "netcdf"
    COPC = "copc"
    STAC_ITEM = "stac_item"
    STAC_COLLECTION = "stac_collection"
    STAC_CATALOG = "stac_catalog"
    GEOJSON = "geojson"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Magic byte signatures
# ---------------------------------------------------------------------------

#: Map of magic byte prefixes to candidate format types. Order matters —
#: first match wins. Entries that map to multiple possible formats (e.g.
#: TIFF can be GeoTIFF or COG) are resolved by content inspection.
_MAGIC_BYTES: list[tuple[bytes, FormatType]] = [
    # TIFF little-endian (GeoTIFF / COG — disambiguated by inspection)
    (b"\x49\x49\x2a\x00", FormatType.GEOTIFF),
    # TIFF big-endian
    (b"\x4d\x4d\x00\x2a", FormatType.GEOTIFF),
    # BigTIFF little-endian
    (b"\x49\x49\x2b\x00", FormatType.GEOTIFF),
    # BigTIFF big-endian
    (b"\x4d\x4d\x00\x2b", FormatType.GEOTIFF),
    # Apache Parquet (GeoParquet uses the same container)
    (b"PAR1", FormatType.PARQUET),
    # FlatGeobuf
    (b"fgb\x03", FormatType.FLATGEOBUF),
    # NetCDF classic
    (b"\x89HDF", FormatType.NETCDF),
    (b"CDF\x01", FormatType.NETCDF),
    (b"CDF\x02", FormatType.NETCDF),
    # LAS/LAZ header (COPC uses LAS 1.4 container)
    (b"LASF", FormatType.COPC),
]

#: Extension-based fallback lookup.
_EXTENSION_MAP: dict[str, FormatType] = {
    ".tif": FormatType.GEOTIFF,
    ".tiff": FormatType.GEOTIFF,
    ".parquet": FormatType.PARQUET,
    ".geoparquet": FormatType.GEOPARQUET,
    ".fgb": FormatType.FLATGEOBUF,
    ".zarr": FormatType.ZARR,
    ".nc": FormatType.NETCDF,
    ".nc4": FormatType.NETCDF,
    ".netcdf": FormatType.NETCDF,
    ".copc.laz": FormatType.COPC,
    ".laz": FormatType.COPC,
    ".las": FormatType.COPC,
    ".geojson": FormatType.GEOJSON,
    ".json": FormatType.GEOJSON,  # might be STAC — inspector resolves
}


# ---------------------------------------------------------------------------
# Content inspectors (registry pattern)
# ---------------------------------------------------------------------------

#: Registered content inspectors. Each inspector receives the raw header bytes,
#: the current candidate format, and the source path. It returns a more specific
#: FormatType or None to leave the candidate unchanged.
InspectorFn = Callable[[bytes, FormatType, str], FormatType | None]

_inspectors: list[InspectorFn] = []


def register_inspector(fn: InspectorFn) -> InspectorFn:
    """Register a content inspector for format disambiguation.

    Inspectors are called in registration order. The first non-None return
    value replaces the candidate format.

    Parameters:
        fn: A callable ``(header_bytes, candidate_format, source) -> FormatType | None``.

    Returns:
        The same function (allows use as a decorator).
    """
    _inspectors.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Built-in inspectors
# ---------------------------------------------------------------------------


@register_inspector
def _inspect_tiff_for_cog(header: bytes, candidate: FormatType, source: str) -> FormatType | None:
    """Check if a TIFF file is a Cloud Optimized GeoTIFF.

    A true COG has its IFDs and tile data organized for range-read access.
    A minimal heuristic: check for tiled layout by looking for the TileWidth
    tag (0x0142 = 322) in the first IFD. This is a simplified check — full
    COG validation is in the raster domain package.

    Parameters:
        header: First 512 bytes of the file.
        candidate: Current detected format.
        source: File path or URL (for logging).

    Returns:
        ``FormatType.COG`` if tiling indicators are found, else ``None``.
    """
    if candidate != FormatType.GEOTIFF:
        return None

    if len(header) < 16:
        return None

    # TIFF tag 322 (0x0142) = TileWidth — presence indicates tiled layout
    # Search the raw bytes for this tag ID in little-endian and big-endian
    tile_width_le = b"\x42\x01"  # 0x0142 little-endian
    tile_width_be = b"\x01\x42"  # 0x0142 big-endian

    is_little_endian = header[:2] == b"\x49\x49"
    tag_bytes = tile_width_le if is_little_endian else tile_width_be

    if tag_bytes in header:
        logger.debug("Tiled TIFF detected for %s, classifying as COG candidate", source)
        return FormatType.COG

    return None


@register_inspector
def _inspect_parquet_for_geo(
    header: bytes, candidate: FormatType, source: str
) -> FormatType | None:
    """Check if a Parquet file is GeoParquet.

    GeoParquet files contain a ``geo`` key in the Parquet file-level
    key-value metadata. This metadata lives in the file footer (not the
    header), so we read the last 4 KB of the file for local paths.

    In Thrift compact protocol, a 3-character string key is preceded by a
    single-byte length varint ``\\x03``. The pattern ``\\x03geo`` in the
    footer uniquely identifies a GeoParquet ``geo`` metadata key — the
    ``geometry`` key would appear as ``\\x08geometry`` (length 8).

    For remote URLs the footer is not fetched by the header reader, so we
    fall back to the ``.geoparquet`` extension convention.

    Parameters:
        header: First 512 bytes of the file.
        candidate: Current detected format.
        source: File path or URL (for logging).

    Returns:
        ``FormatType.GEOPARQUET`` if the ``geo`` metadata key is found, else ``None``.
    """
    if candidate != FormatType.PARQUET:
        return None

    # Extension hint for remote URLs (no footer available from header bytes)
    source_lower = source.lower()
    if ".geoparquet" in source_lower or source_lower.endswith(".geoparquet"):
        return FormatType.GEOPARQUET

    # For local files, read the footer and check for the geo key
    if not _is_remote(source):
        try:
            path = Path(source)
            file_size = path.stat().st_size
            if file_size < 12:  # too small to be valid Parquet
                return None
            # Read last 4096 bytes — sufficient for nearly all real Parquet footers
            read_start = max(0, file_size - 4096)
            with path.open("rb") as fh:
                fh.seek(read_start)
                footer_region = fh.read()
            # \x03geo = Thrift compact string encoding for the 3-char key "geo"
            if b"\x03geo" in footer_region:
                logger.debug("GeoParquet geo metadata key found in footer of %s", source)
                return FormatType.GEOPARQUET
        except OSError:
            pass

    return None


@register_inspector
def _inspect_json_for_stac(header: bytes, candidate: FormatType, source: str) -> FormatType | None:
    """Check if a JSON file is a STAC document.

    STAC Items, Collections, and Catalogs are JSON files with a ``"type"`` field
    and ``"stac_version"`` field. We check the header bytes for these markers.

    Parameters:
        header: First 512 bytes of the file.
        candidate: Current detected format.
        source: File path or URL (for logging).

    Returns:
        The specific STAC format type, or ``None``.
    """
    if candidate != FormatType.GEOJSON:
        return None

    try:
        text = header.decode("utf-8", errors="ignore")
    except Exception:
        return None

    if '"stac_version"' not in text:
        return None

    if '"type"' not in text:
        return None

    if '"Feature"' in text:
        return FormatType.STAC_ITEM
    if '"Collection"' in text:
        return FormatType.STAC_COLLECTION
    if '"Catalog"' in text:
        return FormatType.STAC_CATALOG

    return None


# ---------------------------------------------------------------------------
# Header reading
# ---------------------------------------------------------------------------


async def _read_header_local(source: str) -> bytes:
    """Read the first 512 bytes from a local file.

    Parameters:
        source: Local file path.

    Returns:
        Up to 512 bytes from the start of the file.

    Raises:
        FormatDetectionError: If the file cannot be read.
    """
    try:
        path = Path(source)
        data = path.read_bytes()
        return data[:512]
    except OSError as exc:
        raise FormatDetectionError(f"Cannot read {source}: {exc}") from exc


async def _read_header_remote(source: str, profile: EarthForgeProfile | None) -> bytes:
    """Read the first 512 bytes from a remote URL via HTTP range request.

    Parameters:
        source: HTTP(S) URL.
        profile: Optional profile for HTTP client configuration.

    Returns:
        Up to 512 bytes from the start of the file.

    Raises:
        FormatDetectionError: If the fetch fails.
    """
    from earthforge.core.config import EarthForgeProfile as _Profile
    from earthforge.core.http import get_bytes

    if profile is None:
        profile = _Profile(name="_detect", storage_backend="local")

    try:
        return await get_bytes(profile, source, start=0, end=512)
    except Exception as exc:
        raise FormatDetectionError(f"Cannot fetch header from {source}: {exc}") from exc


def _is_remote(source: str) -> bool:
    """Check whether a source string is a remote URL.

    Parameters:
        source: File path or URL.

    Returns:
        ``True`` if the source starts with ``http://`` or ``https://``.
    """
    return source.startswith(("http://", "https://"))


# ---------------------------------------------------------------------------
# Extension matching
# ---------------------------------------------------------------------------


def _detect_by_extension(source: str) -> FormatType | None:
    """Attempt format detection by file extension.

    Parameters:
        source: File path or URL.

    Returns:
        The detected format, or ``None`` if the extension is unknown.
    """
    # Strip query parameters from URLs
    clean = source.split("?")[0].split("#")[0]
    lower = clean.lower()

    # Check compound extensions first (e.g. .copc.laz)
    for ext, fmt in sorted(_EXTENSION_MAP.items(), key=lambda x: -len(x[0])):
        if lower.endswith(ext):
            return fmt

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def detect(
    source: str,
    *,
    profile: EarthForgeProfile | None = None,
) -> FormatType:
    """Detect the geospatial format of a file or URL.

    Uses a three-stage chain: magic bytes → extension → content inspection.
    For remote URLs, only the first 512 bytes are fetched.

    Parameters:
        source: Local file path or HTTP(S) URL.
        profile: Optional profile for HTTP client configuration (remote URLs).

    Returns:
        The detected :class:`FormatType`.

    Raises:
        FormatDetectionError: If the source cannot be read.
    """
    # Stage 1 + 3: Read header and check magic bytes
    if _is_remote(source):
        header = await _read_header_remote(source, profile)
    else:
        header = await _read_header_local(source)

    # Check magic bytes
    candidate: FormatType | None = None
    for magic, fmt in _MAGIC_BYTES:
        if header.startswith(magic):
            candidate = fmt
            break

    # Stage 2: Extension fallback
    if candidate is None:
        candidate = _detect_by_extension(source)

    # If still nothing, return UNKNOWN
    if candidate is None:
        logger.debug("No format detected for %s", source)
        return FormatType.UNKNOWN

    # Stage 3: Content inspection to refine the candidate
    for inspector in _inspectors:
        refined = inspector(header, candidate, source)
        if refined is not None:
            candidate = refined
            break

    logger.debug("Detected format %s for %s", candidate, source)
    return candidate


def detect_sync(
    source: str,
    *,
    profile: EarthForgeProfile | None = None,
) -> FormatType:
    """Synchronous convenience wrapper for :func:`detect`.

    Parameters:
        source: Local file path or HTTP(S) URL.
        profile: Optional profile for HTTP client configuration.

    Returns:
        The detected :class:`FormatType`.

    Raises:
        FormatDetectionError: If the source cannot be read.
    """
    return asyncio.run(detect(source, profile=profile))
