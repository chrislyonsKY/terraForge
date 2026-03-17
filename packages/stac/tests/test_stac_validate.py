"""Tests for STAC validation module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from earthforge.stac.errors import StacValidationError
from earthforge.stac.validate import StacValidationResult, validate_stac


def _make_profile() -> object:
    """Create a minimal profile for testing."""
    from earthforge.core.config import EarthForgeProfile

    return EarthForgeProfile(name="test", storage_backend="local")


def _valid_item_dict() -> dict:
    """Return a minimal valid STAC Item dict."""
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "id": "test-item-001",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-85.5, 37.0], [-84.0, 37.0], [-84.0, 38.5], [-85.5, 38.5], [-85.5, 37.0]]
            ],
        },
        "bbox": [-85.5, 37.0, -84.0, 38.5],
        "properties": {"datetime": "2025-06-15T00:00:00Z"},
        "links": [
            {
                "rel": "self",
                "href": "https://example.com/items/test-item-001",
                "type": "application/json",
            },
            {"rel": "root", "href": "https://example.com", "type": "application/json"},
        ],
        "assets": {
            "B04": {
                "href": "https://example.com/B04.tif",
                "type": "image/tiff; application=geotiff",
            }
        },
    }


def _valid_collection_dict() -> dict:
    """Return a minimal valid STAC Collection dict."""
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "id": "test-collection",
        "description": "A test collection",
        "license": "proprietary",
        "links": [
            {
                "rel": "self",
                "href": "https://example.com/collections/test",
                "type": "application/json",
            },
        ],
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [["2020-01-01T00:00:00Z", None]]},
        },
    }


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class TestValidateStacItem:
    """Tests for STAC Item validation."""

    def test_valid_item_from_file(self, tmp_path: Path) -> None:
        item_path = tmp_path / "item.json"
        item_path.write_text(json.dumps(_valid_item_dict()), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(item_path)))

        assert isinstance(result, StacValidationResult)
        assert result.is_valid is True
        assert result.stac_type == "Item"
        assert result.stac_version == "1.0.0"
        assert "[PASS]" in result.summary

    def test_invalid_item_missing_fields(self, tmp_path: Path) -> None:
        item_dict = _valid_item_dict()
        del item_dict["geometry"]
        del item_dict["bbox"]

        item_path = tmp_path / "bad_item.json"
        item_path.write_text(json.dumps(item_dict), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(item_path)))

        assert result.is_valid is False
        assert "[FAIL]" in result.summary

    def test_item_without_self_link(self, tmp_path: Path) -> None:
        item_dict = _valid_item_dict()
        item_dict["links"] = [{"rel": "root", "href": "https://example.com"}]

        item_path = tmp_path / "no_self.json"
        item_path.write_text(json.dumps(item_dict), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(item_path)))

        warn_checks = [c for c in result.checks if "[WARN]" in c.status]
        assert len(warn_checks) >= 1

    def test_item_with_extensions(self, tmp_path: Path) -> None:
        item_dict = _valid_item_dict()
        item_dict["stac_extensions"] = ["https://stac-extensions.github.io/eo/v1.1.0/schema.json"]
        item_dict["properties"]["eo:cloud_cover"] = 15.0

        item_path = tmp_path / "eo_item.json"
        item_path.write_text(json.dumps(item_dict), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(item_path)))

        assert len(result.extensions_validated) == 1


class TestValidateStacCollection:
    """Tests for STAC Collection validation."""

    def test_valid_collection(self, tmp_path: Path) -> None:
        coll_path = tmp_path / "collection.json"
        coll_path.write_text(json.dumps(_valid_collection_dict()), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(coll_path)))

        assert result.is_valid is True
        assert result.stac_type == "Collection"

    def test_invalid_collection_missing_license(self, tmp_path: Path) -> None:
        coll_dict = _valid_collection_dict()
        del coll_dict["license"]

        coll_path = tmp_path / "bad_coll.json"
        coll_path.write_text(json.dumps(coll_dict), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(coll_path)))

        assert result.is_valid is False


class TestValidateStacErrors:
    """Tests for error handling in STAC validation."""

    def test_file_not_found(self) -> None:
        profile = _make_profile()
        with pytest.raises(StacValidationError, match="File not found"):
            _run(validate_stac(profile, "/nonexistent/path.json"))

    def test_invalid_json(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not json at all {{{", encoding="utf-8")

        profile = _make_profile()
        with pytest.raises(StacValidationError, match="Invalid JSON"):
            _run(validate_stac(profile, str(bad_path)))

    def test_non_stac_json(self, tmp_path: Path) -> None:
        non_stac = tmp_path / "random.json"
        non_stac.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(non_stac)))

        assert result.is_valid is False
        assert result.stac_type == "Unknown"


class TestStatusMarkers:
    """Verify all check statuses include text markers."""

    def test_all_checks_have_text_markers(self, tmp_path: Path) -> None:
        item_path = tmp_path / "item.json"
        item_path.write_text(json.dumps(_valid_item_dict()), encoding="utf-8")

        profile = _make_profile()
        result = _run(validate_stac(profile, str(item_path)))

        for check in result.checks:
            assert any(
                marker in check.status
                for marker in ["[PASS]", "[FAIL]", "[WARN]", "[INFO]", "[SKIP]"]
            ), f"Check '{check.check}' has no text status marker: {check.status}"
