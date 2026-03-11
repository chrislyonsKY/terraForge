"""Tests for STAC item and collection info inspection.

Uses respx to mock HTTP responses, matching the EarthForge testing convention.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.errors import StacError
from earthforge.stac.info import (
    StacCollectionInfo,
    StacItemInfo,
    inspect_stac_collection,
    inspect_stac_item,
)


def _make_profile() -> EarthForgeProfile:
    return EarthForgeProfile(name="test", stac_api="https://example.com/stac")


SAMPLE_ITEM = {
    "type": "Feature",
    "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/eo/v1.1.0/schema.json"],
    "id": "S2A_MSIL2A_20240615",
    "collection": "sentinel-2-l2a",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-85, 37], [-84, 37], [-84, 38], [-85, 38], [-85, 37]]],
    },
    "bbox": [-85.0, 37.0, -84.0, 38.0],
    "properties": {
        "datetime": "2024-06-15T10:30:00Z",
        "eo:cloud_cover": 12.5,
        "platform": "sentinel-2a",
        "constellation": "sentinel-2",
        "gsd": 10,
        "proj:epsg": 32617,
    },
    "assets": {
        "visual": {
            "href": "https://example.com/visual.tif",
            "type": "image/tiff; application=geotiff",
            "title": "True Color Image",
            "roles": ["visual"],
        },
        "B04": {
            "href": "https://example.com/B04.tif",
            "type": "image/tiff",
            "title": "Band 4 (Red)",
            "roles": ["data"],
        },
    },
    "links": [
        {"rel": "self", "href": "https://example.com/items/S2A_MSIL2A_20240615"},
    ],
}

SAMPLE_COLLECTION = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "id": "sentinel-2-l2a",
    "title": "Sentinel-2 Level-2A",
    "description": "Global Sentinel-2 surface reflectance data.",
    "license": "proprietary",
    "extent": {
        "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
        "temporal": {"interval": [["2015-06-27T00:00:00Z", None]]},
    },
}


class TestInspectStacItem:
    """Tests for STAC item inspection."""

    @respx.mock
    async def test_basic_item(self) -> None:
        url = "https://example.com/items/S2A_MSIL2A_20240615"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        profile = _make_profile()
        info = await inspect_stac_item(profile, url)

        assert isinstance(info, StacItemInfo)
        assert info.id == "S2A_MSIL2A_20240615"
        assert info.collection == "sentinel-2-l2a"
        assert info.stac_version == "1.0.0"

    @respx.mock
    async def test_item_datetime(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert info.datetime == "2024-06-15T10:30:00Z"

    @respx.mock
    async def test_item_bbox(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert info.bbox == [-85.0, 37.0, -84.0, 38.0]

    @respx.mock
    async def test_item_geometry_type(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert info.geometry_type == "Polygon"

    @respx.mock
    async def test_item_properties(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert info.properties["eo:cloud_cover"] == 12.5
        assert info.properties["platform"] == "sentinel-2a"

    @respx.mock
    async def test_item_assets(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert info.asset_count == 2
        keys = [a.key for a in info.assets]
        assert "visual" in keys
        assert "B04" in keys

    @respx.mock
    async def test_item_extensions(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        assert len(info.stac_extensions) == 1
        assert "eo" in info.stac_extensions[0]

    @respx.mock
    async def test_not_a_feature_raises(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json={"type": "Collection"}))

        with pytest.raises(StacError, match=r"not.*STAC item"):
            await inspect_stac_item(_make_profile(), url)

    @respx.mock
    async def test_json_serializable(self) -> None:
        url = "https://example.com/items/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_ITEM))

        info = await inspect_stac_item(_make_profile(), url)
        dumped = info.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["id"] == "S2A_MSIL2A_20240615"


class TestInspectStacCollection:
    """Tests for STAC collection inspection."""

    @respx.mock
    async def test_basic_collection(self) -> None:
        url = "https://example.com/collections/sentinel-2-l2a"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_COLLECTION))

        info = await inspect_stac_collection(_make_profile(), url)

        assert isinstance(info, StacCollectionInfo)
        assert info.id == "sentinel-2-l2a"
        assert info.title == "Sentinel-2 Level-2A"
        assert info.license == "proprietary"

    @respx.mock
    async def test_collection_spatial_extent(self) -> None:
        url = "https://example.com/collections/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_COLLECTION))

        info = await inspect_stac_collection(_make_profile(), url)
        assert info.extent_spatial == [-180.0, -90.0, 180.0, 90.0]

    @respx.mock
    async def test_collection_temporal_extent(self) -> None:
        url = "https://example.com/collections/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_COLLECTION))

        info = await inspect_stac_collection(_make_profile(), url)
        assert len(info.extent_temporal) == 2
        assert info.extent_temporal[0] == "2015-06-27T00:00:00Z"

    @respx.mock
    async def test_json_serializable(self) -> None:
        url = "https://example.com/collections/test"
        respx.get(url).mock(return_value=httpx.Response(200, json=SAMPLE_COLLECTION))

        info = await inspect_stac_collection(_make_profile(), url)
        dumped = info.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["id"] == "sentinel-2-l2a"
