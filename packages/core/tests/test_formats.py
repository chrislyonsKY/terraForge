"""Tests for EarthForge format detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthforge.core.errors import FormatDetectionError
from earthforge.core.formats import (
    FormatType,
    _detect_by_extension,
    _inspect_json_for_stac,
    _inspect_parquet_for_geo,
    _inspect_tiff_for_cog,
    detect,
)

# ---------------------------------------------------------------------------
# FormatType enum
# ---------------------------------------------------------------------------


class TestFormatType:
    """Tests for the FormatType StrEnum."""

    def test_string_values(self) -> None:
        assert FormatType.COG == "cog"
        assert FormatType.GEOTIFF == "geotiff"
        assert FormatType.GEOPARQUET == "geoparquet"
        assert FormatType.UNKNOWN == "unknown"

    def test_from_string(self) -> None:
        assert FormatType("cog") == FormatType.COG


# ---------------------------------------------------------------------------
# Extension detection
# ---------------------------------------------------------------------------


class TestExtensionDetection:
    """Tests for extension-based format lookup."""

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("file.tif", FormatType.GEOTIFF),
            ("file.tiff", FormatType.GEOTIFF),
            ("data.parquet", FormatType.PARQUET),
            ("data.geoparquet", FormatType.GEOPARQUET),
            ("layer.fgb", FormatType.FLATGEOBUF),
            ("store.zarr", FormatType.ZARR),
            ("climate.nc", FormatType.NETCDF),
            ("points.copc.laz", FormatType.COPC),
            ("boundary.geojson", FormatType.GEOJSON),
        ],
    )
    def test_known_extensions(self, source: str, expected: FormatType) -> None:
        assert _detect_by_extension(source) == expected

    def test_unknown_extension(self) -> None:
        assert _detect_by_extension("readme.md") is None

    def test_url_with_query_params(self) -> None:
        url = "https://example.com/file.tif?token=abc&expires=123"
        assert _detect_by_extension(url) == FormatType.GEOTIFF

    def test_compound_extension_priority(self) -> None:
        """`.copc.laz` should match before `.laz`."""
        assert _detect_by_extension("points.copc.laz") == FormatType.COPC


# ---------------------------------------------------------------------------
# Magic byte detection
# ---------------------------------------------------------------------------


class TestMagicByteDetection:
    """Tests for magic-byte-based detection using real file headers."""

    async def test_tiff_little_endian(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tif"
        # TIFF LE header — no tile tags, so stays as GEOTIFF
        f.write_bytes(b"\x49\x49\x2a\x00" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.GEOTIFF

    async def test_tiff_big_endian(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tif"
        f.write_bytes(b"\x4d\x4d\x00\x2a" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.GEOTIFF

    async def test_bigtiff(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tif"
        f.write_bytes(b"\x49\x49\x2b\x00" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.GEOTIFF

    async def test_parquet(self, tmp_path: Path) -> None:
        f = tmp_path / "test.parquet"
        f.write_bytes(b"PAR1" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.PARQUET

    async def test_flatgeobuf(self, tmp_path: Path) -> None:
        f = tmp_path / "test.fgb"
        f.write_bytes(b"fgb\x03" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.FLATGEOBUF

    async def test_netcdf_hdf(self, tmp_path: Path) -> None:
        f = tmp_path / "test.nc"
        f.write_bytes(b"\x89HDF" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.NETCDF

    async def test_las(self, tmp_path: Path) -> None:
        f = tmp_path / "test.las"
        f.write_bytes(b"LASF" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.COPC

    async def test_unknown_magic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"\xff\xfe\xfd\xfc" + b"\x00" * 508)
        result = await detect(str(f))
        assert result == FormatType.UNKNOWN

    async def test_unreadable_file(self) -> None:
        with pytest.raises(FormatDetectionError, match="Cannot read"):
            await detect("/nonexistent/path/file.tif")


# ---------------------------------------------------------------------------
# COG inspector
# ---------------------------------------------------------------------------


class TestCogInspector:
    """Tests for the TIFF → COG content inspector."""

    def test_tiled_tiff_detected_as_cog(self) -> None:
        # Header with TileWidth tag (0x0142) in little-endian
        header = b"\x49\x49\x2a\x00" + b"\x00" * 20 + b"\x42\x01" + b"\x00" * 486
        result = _inspect_tiff_for_cog(header, FormatType.GEOTIFF, "test.tif")
        assert result == FormatType.COG

    def test_untiled_tiff_stays_geotiff(self) -> None:
        header = b"\x49\x49\x2a\x00" + b"\x00" * 508
        result = _inspect_tiff_for_cog(header, FormatType.GEOTIFF, "test.tif")
        assert result is None

    def test_ignores_non_tiff(self) -> None:
        result = _inspect_tiff_for_cog(b"PAR1" + b"\x00" * 508, FormatType.PARQUET, "x")
        assert result is None

    def test_short_header(self) -> None:
        result = _inspect_tiff_for_cog(b"\x49\x49", FormatType.GEOTIFF, "x")
        assert result is None


# ---------------------------------------------------------------------------
# GeoParquet inspector
# ---------------------------------------------------------------------------


class TestGeoParquetInspector:
    """Tests for the Parquet → GeoParquet content inspector."""

    def test_geoparquet_extension(self) -> None:
        result = _inspect_parquet_for_geo(b"PAR1", FormatType.PARQUET, "data.geoparquet")
        assert result == FormatType.GEOPARQUET

    def test_geoparquet_in_path(self) -> None:
        result = _inspect_parquet_for_geo(
            b"PAR1", FormatType.PARQUET, "/data/geoparquet/part-0.parquet"
        )
        assert result == FormatType.GEOPARQUET

    def test_plain_parquet_stays(self) -> None:
        result = _inspect_parquet_for_geo(b"PAR1", FormatType.PARQUET, "plain.parquet")
        assert result is None

    def test_ignores_non_parquet(self) -> None:
        result = _inspect_parquet_for_geo(b"PAR1", FormatType.GEOTIFF, "x.geoparquet")
        assert result is None


# ---------------------------------------------------------------------------
# STAC inspector
# ---------------------------------------------------------------------------


class TestStacInspector:
    """Tests for the JSON → STAC content inspector."""

    def test_stac_item(self) -> None:
        header = b'{"type": "Feature", "stac_version": "1.0.0", "id": "test"}'
        result = _inspect_json_for_stac(header, FormatType.GEOJSON, "item.json")
        assert result == FormatType.STAC_ITEM

    def test_stac_collection(self) -> None:
        header = b'{"type": "Collection", "stac_version": "1.0.0"}'
        result = _inspect_json_for_stac(header, FormatType.GEOJSON, "coll.json")
        assert result == FormatType.STAC_COLLECTION

    def test_stac_catalog(self) -> None:
        header = b'{"type": "Catalog", "stac_version": "1.0.0"}'
        result = _inspect_json_for_stac(header, FormatType.GEOJSON, "cat.json")
        assert result == FormatType.STAC_CATALOG

    def test_plain_geojson_stays(self) -> None:
        header = b'{"type": "FeatureCollection", "features": []}'
        result = _inspect_json_for_stac(header, FormatType.GEOJSON, "data.geojson")
        assert result is None

    def test_ignores_non_geojson(self) -> None:
        header = b'{"type": "Feature", "stac_version": "1.0.0"}'
        result = _inspect_json_for_stac(header, FormatType.PARQUET, "x.json")
        assert result is None


# ---------------------------------------------------------------------------
# Full detection chain (integration of stages)
# ---------------------------------------------------------------------------


class TestDetectChain:
    """End-to-end tests for the full detection pipeline."""

    async def test_tiled_tiff_detected_as_cog(self, tmp_path: Path) -> None:
        """A TIFF with tile tags should be detected as COG, not just GEOTIFF."""
        f = tmp_path / "tiled.tif"
        # TIFF LE header with TileWidth tag embedded
        header = bytearray(512)
        header[0:4] = b"\x49\x49\x2a\x00"
        header[30:32] = b"\x42\x01"  # TileWidth tag
        f.write_bytes(bytes(header))
        result = await detect(str(f))
        assert result == FormatType.COG

    async def test_extension_fallback(self, tmp_path: Path) -> None:
        """Unknown magic bytes but known extension should use extension."""
        f = tmp_path / "store.zarr"
        f.write_bytes(b"\x00" * 100)
        result = await detect(str(f))
        assert result == FormatType.ZARR

    async def test_stac_item_json(self, tmp_path: Path) -> None:
        """A JSON file with STAC markers should be detected as STAC_ITEM."""
        f = tmp_path / "item.json"
        content = b'{"type": "Feature", "stac_version": "1.0.0", "id": "S2A"}'
        f.write_bytes(content)
        result = await detect(str(f))
        assert result == FormatType.STAC_ITEM
