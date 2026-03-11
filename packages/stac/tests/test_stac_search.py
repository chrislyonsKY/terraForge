"""Tests for STAC catalog search.

Uses mocked pystac-client to avoid real network calls in unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.errors import StacError, StacSearchError
from earthforge.stac.search import SearchResult, search_catalog


def _make_profile(stac_api: str | None = "https://earth-search.aws.element84.com/v1") -> (
    EarthForgeProfile
):
    return EarthForgeProfile(name="test", stac_api=stac_api)


def _make_mock_item(
    item_id: str = "S2A_test",
    collection_id: str = "sentinel-2-l2a",
    dt: datetime | None = None,
    bbox: list[float] | None = None,
) -> MagicMock:
    """Create a mock pystac Item."""
    item = MagicMock()
    item.id = item_id
    item.collection_id = collection_id
    item.datetime = dt or datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC)
    item.properties = {"datetime": "2024-06-15T10:30:00Z"}
    item.bbox = bbox or [-85.0, 37.0, -84.0, 38.0]

    # Assets
    asset = MagicMock()
    asset.href = "https://example.com/B04.tif"
    asset.media_type = "image/tiff"
    asset.title = "Band 4"
    item.assets = {"B04": asset}

    # Links
    link = MagicMock()
    link.rel = "self"
    link.href = f"https://example.com/items/{item_id}"
    item.links = [link]

    return item


class TestSearchCatalog:
    """Tests for STAC search functionality."""

    @patch("pystac_client.Client")
    async def test_basic_search(self, mock_client_cls: MagicMock) -> None:
        """Search returns structured results."""
        mock_item = _make_mock_item()
        mock_search = MagicMock()
        mock_search.item_collection.return_value = [mock_item]
        mock_search.matched.return_value = 1

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        result = await search_catalog(
            profile,
            collections=["sentinel-2-l2a"],
            bbox=[-85.0, 37.0, -84.0, 38.0],
            max_items=10,
        )

        assert isinstance(result, SearchResult)
        assert result.returned == 1
        assert result.matched == 1
        assert result.items[0].id == "S2A_test"
        assert result.items[0].collection == "sentinel-2-l2a"
        assert result.items[0].asset_count == 1

    @patch("pystac_client.Client")
    async def test_empty_search(self, mock_client_cls: MagicMock) -> None:
        """Empty search returns zero items."""
        mock_search = MagicMock()
        mock_search.item_collection.return_value = []
        mock_search.matched.return_value = 0

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        result = await search_catalog(profile, collections=["nonexistent"])

        assert result.returned == 0
        assert result.items == []

    @patch("pystac_client.Client")
    async def test_search_with_datetime(self, mock_client_cls: MagicMock) -> None:
        """Datetime filter is passed to pystac-client."""
        mock_search = MagicMock()
        mock_search.item_collection.return_value = []
        mock_search.matched.return_value = 0

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        await search_catalog(
            profile,
            datetime_range="2024-01-01/2024-06-30",
        )

        mock_catalog.search.assert_called_once()
        call_kwargs = mock_catalog.search.call_args
        assert call_kwargs.kwargs.get("datetime") == "2024-01-01/2024-06-30"

    @patch("pystac_client.Client")
    async def test_search_assets_populated(self, mock_client_cls: MagicMock) -> None:
        """Assets are included in search result items."""
        mock_item = _make_mock_item()
        mock_search = MagicMock()
        mock_search.item_collection.return_value = [mock_item]
        mock_search.matched.return_value = 1

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        result = await search_catalog(profile, max_items=1)

        assert len(result.items[0].assets) == 1
        assert result.items[0].assets[0].key == "B04"
        assert result.items[0].assets[0].media_type == "image/tiff"

    @patch("pystac_client.Client")
    async def test_search_self_link(self, mock_client_cls: MagicMock) -> None:
        """Self link is extracted from item links."""
        mock_item = _make_mock_item(item_id="test-123")
        mock_search = MagicMock()
        mock_search.item_collection.return_value = [mock_item]
        mock_search.matched.return_value = 1

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        result = await search_catalog(profile, max_items=1)

        assert result.items[0].self_link == "https://example.com/items/test-123"

    async def test_no_stac_api_raises(self) -> None:
        """Profile without stac_api raises StacError."""
        profile = _make_profile(stac_api=None)
        with pytest.raises(StacError, match="no stac_api configured"):
            await search_catalog(profile)

    @patch("pystac_client.Client")
    async def test_connection_failure_raises(self, mock_client_cls: MagicMock) -> None:
        """Connection failure wraps as StacSearchError."""
        mock_client_cls.open.side_effect = ConnectionError("refused")

        profile = _make_profile()
        with pytest.raises(StacSearchError, match="Failed to connect"):
            await search_catalog(profile)

    @patch("pystac_client.Client")
    async def test_matched_count_unavailable(self, mock_client_cls: MagicMock) -> None:
        """When API doesn't report matched count, it's None."""
        mock_search = MagicMock()
        mock_search.item_collection.return_value = []
        mock_search.matched.side_effect = Exception("not supported")

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search
        mock_client_cls.open.return_value = mock_catalog

        profile = _make_profile()
        result = await search_catalog(profile)
        assert result.matched is None

    async def test_json_serializable(self) -> None:
        """SearchResult must be JSON-serializable."""
        import json

        result = SearchResult(
            api_url="https://example.com",
            matched=1,
            returned=1,
            items=[
                SearchResultItem(
                    id="test",
                    collection="col",
                    datetime="2024-01-01T00:00:00Z",
                    bbox=[-85.0, 37.0, -84.0, 38.0],
                    asset_count=0,
                )
            ],
        )
        dumped = result.model_dump(mode="json")
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed["returned"] == 1


# Import here for the serialization test
from earthforge.stac.search import SearchResultItem  # noqa: E402
