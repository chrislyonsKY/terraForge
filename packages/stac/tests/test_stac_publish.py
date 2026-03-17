"""Tests for STAC publish module."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from earthforge.stac.errors import StacPublishError
from earthforge.stac.publish import PublishResult, publish_item


def _run(coro):
    return asyncio.run(coro)


def _make_profile(stac_api: str = "https://example.com/stac") -> object:
    from earthforge.core.config import EarthForgeProfile

    return EarthForgeProfile(name="test", stac_api=stac_api, storage_backend="local")


def _valid_item() -> dict:
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "test-item-001",
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "bbox": [-1, -1, 1, 1],
        "properties": {"datetime": "2025-01-01T00:00:00Z"},
        "links": [],
        "assets": {},
        "collection": "test-collection",
    }


class TestPublishItem:
    @respx.mock
    def test_successful_create(self) -> None:
        respx.post("https://example.com/stac/collections/test-collection/items").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "test-item-001",
                    "links": [{"rel": "self", "href": "https://example.com/stac/items/test-item-001"}],
                },
            )
        )

        profile = _make_profile()
        result = _run(publish_item(profile, _valid_item()))

        assert isinstance(result, PublishResult)
        assert result.action == "created"
        assert result.item_id == "test-item-001"
        assert result.status_code == 201

    @respx.mock
    def test_upsert_on_conflict(self) -> None:
        respx.post("https://example.com/stac/collections/test-collection/items").mock(
            return_value=httpx.Response(409, text="Conflict")
        )
        respx.put("https://example.com/stac/collections/test-collection/items/test-item-001").mock(
            return_value=httpx.Response(200, json={"id": "test-item-001", "links": []})
        )

        profile = _make_profile()
        result = _run(publish_item(profile, _valid_item()))

        assert result.action == "updated"
        assert result.status_code == 200

    @respx.mock
    def test_post_failure(self) -> None:
        respx.post("https://example.com/stac/collections/test-collection/items").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        profile = _make_profile()
        with pytest.raises(StacPublishError, match="POST failed"):
            _run(publish_item(profile, _valid_item()))


class TestValidation:
    def test_no_api_url(self) -> None:
        from earthforge.core.config import EarthForgeProfile

        profile = EarthForgeProfile(name="test", stac_api="", storage_backend="local")

        with pytest.raises(StacPublishError, match="No STAC API URL"):
            _run(publish_item(profile, _valid_item(), api_url=""))

    def test_no_collection(self) -> None:
        profile = _make_profile()
        item = _valid_item()
        del item["collection"]

        with pytest.raises(StacPublishError, match="No collection_id"):
            _run(publish_item(profile, item))

    def test_no_item_id(self) -> None:
        profile = _make_profile()
        item = _valid_item()
        del item["id"]

        with pytest.raises(StacPublishError, match="must have an 'id'"):
            _run(publish_item(profile, item))
