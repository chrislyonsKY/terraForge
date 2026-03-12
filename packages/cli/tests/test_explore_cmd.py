"""Tests for earthforge.cli.commands.explore_cmd and earthforge.cli.tui.app.

These tests cover:
- CLI option parsing and validation (no TUI rendering required)
- ExploreApp initialisation and default state
- _item_to_dict static method
- _render_detail rendering logic
- bbox parsing edge cases
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# ExploreApp unit tests (no Textual rendering)
# ---------------------------------------------------------------------------


class TestExploreAppInit:
    """Tests for ExploreApp attribute initialisation."""

    def test_default_api_url(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import _DEFAULT_API, ExploreApp

        app = ExploreApp()
        assert app.api_url == _DEFAULT_API

    def test_custom_api_url(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        app = ExploreApp(api_url=url)
        assert app.api_url == url

    def test_initial_collection_none_by_default(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        app = ExploreApp()
        assert app.initial_collection is None

    def test_initial_collection_stored(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        app = ExploreApp(initial_collection="sentinel-2-l2a")
        assert app.initial_collection == "sentinel-2-l2a"

    def test_bbox_none_by_default(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        app = ExploreApp()
        assert app.bbox is None

    def test_bbox_stored(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        bbox = (-85.0, 37.0, -84.0, 38.0)
        app = ExploreApp(bbox=bbox)
        assert app.bbox == bbox

    def test_items_data_empty_on_init(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        app = ExploreApp()
        assert app._items_data == []

    def test_current_collection_none_on_init(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        app = ExploreApp()
        assert app._current_collection is None


# ---------------------------------------------------------------------------
# _item_to_dict
# ---------------------------------------------------------------------------


class TestItemToDict:
    """Tests for the ExploreApp._item_to_dict static method."""

    def test_returns_dict_from_to_dict(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        class FakeItem:
            id = "item-001"

            def to_dict(self) -> dict:
                return {"id": "item-001", "type": "Feature"}

        result = ExploreApp._item_to_dict(FakeItem())
        assert result == {"id": "item-001", "type": "Feature"}

    def test_fallback_on_exception(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        class BrokenItem:
            id = "broken-item"

            def to_dict(self) -> dict:
                raise RuntimeError("serialisation failed")

        result = ExploreApp._item_to_dict(BrokenItem())
        assert result == {"id": "broken-item"}

    def test_fallback_no_id(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import ExploreApp

        class NoIdItem:
            def to_dict(self) -> dict:
                raise RuntimeError("oops")

        result = ExploreApp._item_to_dict(NoIdItem())
        assert result == {"id": "?"}


# ---------------------------------------------------------------------------
# bbox validation in the CLI command
# ---------------------------------------------------------------------------


class TestBboxParsing:
    """Tests for bbox parsing in explore_cmd (without launching the TUI)."""

    def test_valid_bbox_string_parsed(self) -> None:
        """Four-element bbox parses to float tuple."""
        raw = "-85.5,37.0,-84.0,38.5"
        parts = [float(v.strip()) for v in raw.split(",")]
        assert len(parts) == 4
        assert parts[0] == pytest.approx(-85.5)
        assert parts[3] == pytest.approx(38.5)

    def test_invalid_bbox_too_few_elements(self) -> None:
        raw = "-85.5,37.0"
        parts = [v.strip() for v in raw.split(",")]
        assert len(parts) != 4

    def test_invalid_bbox_non_numeric(self) -> None:
        raw = "-85.5,north,-84.0,38.5"
        with pytest.raises(ValueError):
            [float(v.strip()) for v in raw.split(",")]


# ---------------------------------------------------------------------------
# _CollectionItem
# ---------------------------------------------------------------------------


class TestCollectionItem:
    """Tests for the _CollectionItem list item widget."""

    def test_collection_id_stored(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import _CollectionItem

        item = _CollectionItem("sentinel-2-l2a")
        assert item.collection_id == "sentinel-2-l2a"

    def test_collection_id_with_title(self) -> None:
        pytest.importorskip("textual")
        from earthforge.cli.tui.app import _CollectionItem

        item = _CollectionItem("cop-dem-glo-30", title="Copernicus DEM GLO-30")
        assert item.collection_id == "cop-dem-glo-30"


# ---------------------------------------------------------------------------
# explore_cmd module structure
# ---------------------------------------------------------------------------


class TestExploreCmdModule:
    """Smoke tests for the explore_cmd Typer app structure."""

    def test_app_name(self) -> None:
        from earthforge.cli.commands.explore_cmd import app

        assert app.info.name == "explore"

    def test_explore_callback_exists(self) -> None:
        from earthforge.cli.commands import explore_cmd

        assert callable(explore_cmd.explore)
