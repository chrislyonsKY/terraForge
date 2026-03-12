"""EarthForge interactive STAC explorer — Textual TUI application.

Provides a three-panel terminal interface for browsing STAC catalogs:

- **Left panel** — Collection browser (all collections at the API endpoint)
- **Centre panel** — Items table (first 50 items in the selected collection)
- **Right panel** — Item detail viewer (metadata, assets, links)

All STAC I/O is performed in Textual thread-pool workers (``@work(thread=True)``)
so the UI never blocks waiting for network responses. The app connects to any
STAC API that is compliant with the STAC API spec and supported by
``pystac-client``.

Usage::

    from earthforge.cli.tui.app import ExploreApp

    ExploreApp(api_url="https://earth-search.aws.element84.com/v1").run()
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Label, ListItem, ListView, Markdown, Static

logger = logging.getLogger(__name__)

_DEFAULT_API = "https://earth-search.aws.element84.com/v1"

_CSS = """
Screen {
    layout: vertical;
}
#explorer {
    height: 1fr;
}
#collections {
    width: 25%;
    border: solid $primary;
}
#items {
    width: 40%;
    border: solid $primary;
}
#detail {
    width: 35%;
    border: solid $primary;
    overflow-y: auto;
}
.panel-title {
    background: $surface;
    color: $text;
    padding: 0 1;
    text-style: bold;
}
#status {
    height: 1;
    background: $surface;
    padding: 0 1;
    color: $text-muted;
}
"""


class _CollectionItem(ListItem):
    """A :class:`~textual.widgets.ListItem` that carries a collection ID.

    Attributes:
        collection_id: The STAC collection identifier.
    """

    def __init__(self, collection_id: str, title: str | None = None) -> None:
        label = title if title else collection_id
        super().__init__(Label(label))
        self.collection_id = collection_id


class ExploreApp(App[None]):
    """Interactive STAC catalog explorer.

    Three-panel layout: Collections | Items | Item Detail.
    All network I/O is handled in Textual async/thread workers.

    Attributes:
        api_url: STAC API endpoint to connect to.
        initial_collection: Pre-select this collection on startup.
        bbox: Optional bounding-box filter ``(west, south, east, north)``.
    """

    TITLE = "EarthForge Explorer"
    CSS = _CSS

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "filter", "Filter"),
        Binding("tab", "focus_next", "Next panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev panel", show=False),
    ]

    def __init__(
        self,
        api_url: str = _DEFAULT_API,
        initial_collection: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> None:
        super().__init__()
        self.api_url = api_url
        self.initial_collection = initial_collection
        self.bbox = bbox
        self._current_collection: str | None = None
        self._items_data: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Build the three-panel layout."""
        yield Header()
        with Horizontal(id="explorer"):
            with Vertical(id="collections"):
                yield Label(" Collections", classes="panel-title")
                yield ListView(id="collection-list")
            with Vertical(id="items"):
                yield Label(" Items", classes="panel-title")
                yield DataTable(id="item-table", zebra_stripes=True)
            with Vertical(id="detail"):
                yield Label(" Detail", classes="panel-title")
                yield Markdown("", id="item-detail")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Configure columns and kick off the initial collection load."""
        table = self.query_one("#item-table", DataTable)
        table.add_columns("ID", "Datetime", "Cloud", "Assets")
        self._set_status(f"Connecting to {self.api_url} \u2026")
        self.load_collections()

    def _set_status(self, message: str) -> None:
        """Update the status bar text.

        Parameters:
            message: Text to display in the status bar.
        """
        self.query_one("#status", Static).update(message)

    @work(exclusive=True, thread=True)
    def load_collections(self) -> None:
        """Fetch all collections from the STAC API.

        Runs in a thread-pool worker so the UI stays responsive. On
        success, delegates to :meth:`_populate_collections` via
        ``call_from_thread``. On failure, updates the status bar.
        """
        try:
            from pystac_client import Client
        except ImportError:
            self.call_from_thread(
                self._set_status,
                "Error: pystac-client not installed. Run: pip install earthforge[stac]",
            )
            return

        try:
            client = Client.open(self.api_url)
            collections = sorted(client.get_collections(), key=lambda c: c.id)
        except Exception as exc:
            logger.debug("Failed to load collections: %s", exc)
            self.call_from_thread(self._set_status, f"Error loading collections: {exc}")
            return

        self.call_from_thread(self._populate_collections, collections)

    def _populate_collections(self, collections: list[Any]) -> None:
        """Populate the collection list widget.

        Parameters:
            collections: Sorted list of pystac Collection objects.
        """
        list_view = self.query_one("#collection-list", ListView)
        list_view.clear()
        for col in collections:
            list_view.append(_CollectionItem(col.id, getattr(col, "title", None)))

        count = len(collections)
        self._set_status(
            f"Loaded {count} collection{'s' if count != 1 else ''} from {self.api_url}"
        )

        if self.initial_collection:
            for i, col in enumerate(collections):
                if col.id == self.initial_collection:
                    list_view.index = i
                    self._current_collection = col.id
                    self._load_items(col.id)
                    break

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Load items when a collection is selected from the browser.

        Parameters:
            event: Textual selection event carrying the selected ListItem.
        """
        if not isinstance(event.item, _CollectionItem):
            return
        collection_id = event.item.collection_id
        if collection_id == self._current_collection:
            return
        self._current_collection = collection_id
        self._set_status(f"Loading items from {collection_id} \u2026")
        self._load_items(collection_id)

    @work(exclusive=True, thread=True)
    def _load_items(self, collection_id: str) -> None:
        """Fetch up to 50 items from the selected collection.

        Runs in a thread-pool worker. On success, delegates to
        :meth:`_populate_items`. Applies the bbox filter if set.

        Parameters:
            collection_id: The STAC collection to query.
        """
        try:
            from pystac_client import Client
        except ImportError:
            return

        try:
            client = Client.open(self.api_url)
            search_kwargs: dict[str, Any] = {
                "collections": [collection_id],
                "max_items": 50,
            }
            if self.bbox:
                search_kwargs["bbox"] = list(self.bbox)
            search = client.search(**search_kwargs)
            items = list(search.item_collection())
        except Exception as exc:
            logger.debug("Failed to load items for %s: %s", collection_id, exc)
            self.call_from_thread(self._set_status, f"Error loading items: {exc}")
            return

        self.call_from_thread(self._populate_items, items)

    def _populate_items(self, items: list[Any]) -> None:
        """Populate the DataTable from a list of pystac Item objects.

        Parameters:
            items: pystac Item objects to display.
        """
        table = self.query_one("#item-table", DataTable)
        table.clear()
        self._items_data = []

        for item in items:
            dt = ""
            if getattr(item, "datetime", None):
                try:
                    dt = item.datetime.strftime("%Y-%m-%d")
                except Exception:
                    dt = str(item.datetime)[:10]
            elif hasattr(item, "properties") and item.properties.get("datetime"):
                dt = str(item.properties["datetime"])[:10]

            cloud = ""
            if hasattr(item, "properties"):
                cc = item.properties.get("eo:cloud_cover")
                if cc is not None:
                    cloud = f"{cc:.0f}%"

            asset_count = len(item.assets) if hasattr(item, "assets") else 0

            table.add_row(item.id, dt, cloud, str(asset_count))
            self._items_data.append(self._item_to_dict(item))

        count = len(items)
        coll = self._current_collection or "?"
        bbox_note = " (bbox filtered)" if self.bbox else ""
        self._set_status(f"{count} item{'s' if count != 1 else ''} in {coll}{bbox_note}")

    @staticmethod
    def _item_to_dict(item: Any) -> dict[str, Any]:
        """Serialise a pystac Item to a plain dict for the detail panel.

        Parameters:
            item: A pystac Item object.

        Returns:
            JSON-serialisable representation of the item.
        """
        try:
            return item.to_dict()  # type: ignore[no-any-return]
        except Exception:
            return {"id": getattr(item, "id", "?")}

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show item detail when the user selects a row.

        Parameters:
            event: Textual row-selection event carrying the cursor row index.
        """
        row_index = event.cursor_row
        if 0 <= row_index < len(self._items_data):
            self._render_detail(self._items_data[row_index])

    def _render_detail(self, item_dict: dict[str, Any]) -> None:
        """Render item metadata as markdown in the detail panel.

        Parameters:
            item_dict: JSON-serialisable item dict from :meth:`_item_to_dict`.
        """
        item_id = item_dict.get("id", "Unknown")
        props: dict[str, Any] = item_dict.get("properties", {})
        bbox = item_dict.get("bbox")
        links: list[Any] = item_dict.get("links", [])
        assets: dict[str, Any] = item_dict.get("assets", {})

        lines = [f"## {item_id}", ""]

        if props.get("datetime"):
            lines.append(f"**Datetime:** {props['datetime']}")
        if bbox:
            rounded = [round(float(v), 4) for v in bbox]
            lines.append(f"**BBox:** `{rounded}`")
        if props.get("eo:cloud_cover") is not None:
            lines.append(f"**Cloud cover:** {props['eo:cloud_cover']:.1f}%")
        if props.get("platform"):
            lines.append(f"**Platform:** {props['platform']}")
        if props.get("constellation"):
            lines.append(f"**Constellation:** {props['constellation']}")

        if assets:
            lines.extend(["", "### Assets", ""])
            for key, asset_data in assets.items():
                if isinstance(asset_data, dict):
                    mt = asset_data.get("type", "")
                    href = asset_data.get("href", "")
                else:
                    mt, href = "", ""
                lines.append(f"- **{key}** \u2014 `{mt}`")
                if href:
                    lines.append(f"  `{href}`")

        self_link = next(
            (
                lnk.get("href", "")
                for lnk in links
                if isinstance(lnk, dict) and lnk.get("rel") == "self"
            ),
            None,
        )
        if self_link:
            lines.extend(["", f"[View on STAC API]({self_link})"])

        self.query_one("#item-detail", Markdown).update("\n".join(lines))

    def action_refresh(self) -> None:
        """Reload all collections from the STAC API."""
        self._set_status("Refreshing \u2026")
        self.load_collections()

    def action_filter(self) -> None:
        """Notify the user that bbox filtering is set at startup."""
        self._set_status("Use --bbox west,south,east,north when launching explore")
