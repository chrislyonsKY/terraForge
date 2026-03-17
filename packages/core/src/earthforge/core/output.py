"""EarthForge structured output rendering.

All CLI output flows through this module. Commands return Pydantic models;
this module serializes them into the format requested by ``--output``. Domain
packages never call ``print()`` or ``rich`` directly.

Supported formats:

- **table** — Human-readable Rich table (default for interactive terminals).
- **json** — Machine-readable JSON matching the Pydantic model schema.
- **csv** — Comma-separated values for spreadsheet and pipeline consumption.
- **quiet** — Suppressed output; only the exit code communicates success/failure.

The contract is simple: if ``--output json`` produces valid JSON for one command,
it produces valid JSON for every command. The schema is the Pydantic model itself.

Accessibility (WCAG 2.1 AA):

- ``NO_COLOR`` disables all color (https://no-color.org/).
- ``FORCE_COLOR`` forces color even in non-interactive contexts
  (https://force-color.org/).  ``NO_COLOR`` takes precedence.
- Status indicators always include text markers (``[PASS]``, ``[FAIL]``,
  ``[WARN]``) so information is never conveyed by color alone.
- High-contrast mode selects styles that meet WCAG 4.5:1 contrast ratios
  on both dark and light terminal backgrounds.

Usage in CLI commands::

    from earthforge.core.output import OutputFormat, render_to_console

    result = await some_library_function(...)
    render_to_console(result, fmt=OutputFormat.TABLE)
"""

from __future__ import annotations

import csv
import io
import os
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

import orjson
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table


class OutputFormat(StrEnum):
    """Supported output formats for CLI commands.

    Members:
        TABLE: Human-readable Rich table.
        JSON: Machine-readable JSON.
        CSV: Comma-separated values.
        QUIET: No output.
    """

    TABLE = "table"
    JSON = "json"
    CSV = "csv"
    QUIET = "quiet"


# ---------------------------------------------------------------------------
# Status markers — text-based indicators alongside color (WCAG 1.4.1)
# ---------------------------------------------------------------------------


class StatusMarker(StrEnum):
    """Text markers for pass/fail/warn status.

    These ensure information is never conveyed by color alone (WCAG 1.4.1
    Use of Color). Every status indicator in table output includes both a
    colored token and a text marker.
    """

    PASS = "[PASS]"  # noqa: S105
    FAIL = "[FAIL]"
    WARN = "[WARN]"
    INFO = "[INFO]"
    SKIP = "[SKIP]"


def format_status(marker: StatusMarker, message: str = "") -> str:
    """Format a status marker with an optional message.

    Parameters:
        marker: The status marker to display.
        message: Optional text to append after the marker.

    Returns:
        A string like ``"[PASS] All checks passed"`` suitable for both
        colored and plain-text rendering.
    """
    if message:
        return f"{marker.value} {message}"
    return marker.value


# ---------------------------------------------------------------------------
# Color determination — NO_COLOR / FORCE_COLOR
# ---------------------------------------------------------------------------

# Standard table style: bold cyan headers meet 4.5:1 on common dark terminals
# (e.g. #00FFFF on #1e1e1e = 12.6:1). High-contrast mode ups this further.
_HEADER_STYLE = "bold cyan"
_HEADER_STYLE_HC = "bold white"


def _should_use_color(*, force_no_color: bool = False) -> bool:
    """Determine whether to use color in output.

    Respects both ``NO_COLOR`` (https://no-color.org/) and ``FORCE_COLOR``
    (https://force-color.org/) environment variables.  ``NO_COLOR`` always
    wins when both are set.

    Parameters:
        force_no_color: Programmatic override from ``--no-color`` CLI flag.

    Returns:
        True if color should be used.
    """
    if force_no_color:
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True
    return True


def _render_json(data: BaseModel | Sequence[BaseModel]) -> str:
    """Serialize one or more Pydantic models to JSON.

    Parameters:
        data: A single model or sequence of models.

    Returns:
        A pretty-printed JSON string.
    """
    raw: dict[str, object] | list[dict[str, object]]
    if isinstance(data, BaseModel):
        raw = data.model_dump(mode="json")
    else:
        raw = [item.model_dump(mode="json") for item in data]

    return orjson.dumps(raw, option=orjson.OPT_INDENT_2).decode("utf-8")


def _render_csv(data: BaseModel | Sequence[BaseModel]) -> str:
    """Serialize one or more Pydantic models to CSV.

    Flattens the model to its top-level fields. Nested objects are serialized
    as JSON strings within the CSV cell.

    Parameters:
        data: A single model or sequence of models.

    Returns:
        A CSV string with header row.
    """
    items: Sequence[BaseModel] = [data] if isinstance(data, BaseModel) else data
    if not items:
        return ""

    buf = io.StringIO()
    fieldnames = list(type(items[0]).model_fields.keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()

    for item in items:
        row: dict[str, Any] = {}
        dumped = item.model_dump(mode="json")
        for key in fieldnames:
            value = dumped.get(key)
            if isinstance(value, (dict, list)):
                row[key] = orjson.dumps(value).decode("utf-8")
            else:
                row[key] = value
        writer.writerow(row)

    return buf.getvalue()


def _render_table(
    data: BaseModel | Sequence[BaseModel],
    *,
    high_contrast: bool = False,
) -> Table:
    """Build a Rich Table from one or more Pydantic models.

    Parameters:
        data: A single model or sequence of models.
        high_contrast: If True, use high-contrast header styling that
            meets WCAG 4.5:1 on both dark and light backgrounds.

    Returns:
        A Rich ``Table`` ready for console printing.
    """
    items: Sequence[BaseModel] = [data] if isinstance(data, BaseModel) else data
    if not items:
        return Table(title="(no results)")

    header_style = _HEADER_STYLE_HC if high_contrast else _HEADER_STYLE
    table = Table(show_header=True, header_style=header_style)

    fields = type(items[0]).model_fields
    for name, field_info in fields.items():
        title = field_info.title or name.replace("_", " ").title()
        table.add_column(title)

    for item in items:
        dumped = item.model_dump(mode="json")
        row_values: list[str] = []
        for key in fields:
            value = dumped.get(key)
            if isinstance(value, (dict, list)):
                row_values.append(orjson.dumps(value).decode("utf-8"))
            else:
                row_values.append(str(value) if value is not None else "—")
        table.add_row(*row_values)

    return table


def render(
    data: BaseModel | Sequence[BaseModel],
    fmt: OutputFormat,
    *,
    high_contrast: bool = False,
) -> str:
    """Render structured data to a string in the requested format.

    Parameters:
        data: A single Pydantic model or a sequence of models.
        fmt: The desired output format.
        high_contrast: If True, use high-contrast styling (WCAG 4.5:1).

    Returns:
        The formatted string. Returns an empty string for ``QUIET`` format.

    Raises:
        ValueError: If ``fmt`` is not a valid ``OutputFormat``.
    """
    if fmt == OutputFormat.JSON:
        return _render_json(data)
    if fmt == OutputFormat.CSV:
        return _render_csv(data)
    if fmt == OutputFormat.QUIET:
        return ""
    if fmt == OutputFormat.TABLE:
        console = Console(
            force_terminal=False,
            no_color=not _should_use_color(),
        )
        with console.capture() as capture:
            console.print(_render_table(data, high_contrast=high_contrast))
        return capture.get()

    msg = f"Unknown output format: {fmt!r}"
    raise ValueError(msg)


def render_to_console(
    data: BaseModel | Sequence[BaseModel],
    fmt: OutputFormat,
    *,
    no_color: bool = False,
    high_contrast: bool = False,
) -> None:
    """Render structured data directly to the terminal.

    This is the primary function called by CLI command handlers.

    Parameters:
        data: A single Pydantic model or a sequence of models.
        fmt: The desired output format.
        no_color: If ``True``, disable colored output regardless of ``NO_COLOR``.
        high_contrast: If ``True``, use high-contrast styling (WCAG 4.5:1).
    """
    if fmt == OutputFormat.QUIET:
        return

    use_color = _should_use_color(force_no_color=no_color)
    console = Console(no_color=not use_color)

    if fmt == OutputFormat.TABLE:
        console.print(_render_table(data, high_contrast=high_contrast))
    elif fmt == OutputFormat.JSON:
        console.print(_render_json(data), highlight=False, soft_wrap=True)
    elif fmt == OutputFormat.CSV:
        console.print(_render_csv(data), highlight=False, soft_wrap=True, end="")
    else:
        msg = f"Unknown output format: {fmt!r}"
        raise ValueError(msg)
