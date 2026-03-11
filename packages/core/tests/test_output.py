"""Tests for the EarthForge output rendering module."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from earthforge.core.output import OutputFormat, render, render_to_console

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class SampleInfo(BaseModel):
    """A minimal model for testing output rendering."""

    name: str
    size: int
    crs: str | None = None
    tags: list[str] = []


class NestedInfo(BaseModel):
    """Model with nested structure for testing serialization."""

    title: str
    metadata: dict[str, str] = {}


# ---------------------------------------------------------------------------
# OutputFormat enum
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Tests for the OutputFormat StrEnum."""

    def test_values(self) -> None:
        assert OutputFormat.TABLE == "table"
        assert OutputFormat.JSON == "json"
        assert OutputFormat.CSV == "csv"
        assert OutputFormat.QUIET == "quiet"

    def test_from_string(self) -> None:
        assert OutputFormat("json") == OutputFormat.JSON


# ---------------------------------------------------------------------------
# JSON rendering
# ---------------------------------------------------------------------------


class TestJsonRendering:
    """Tests for JSON output."""

    def test_single_model(self) -> None:
        info = SampleInfo(name="test.tif", size=1024, crs="EPSG:4326")
        result = render(info, OutputFormat.JSON)
        parsed = json.loads(result)
        assert parsed["name"] == "test.tif"
        assert parsed["size"] == 1024
        assert parsed["crs"] == "EPSG:4326"

    def test_list_of_models(self) -> None:
        items = [
            SampleInfo(name="a.tif", size=100),
            SampleInfo(name="b.tif", size=200),
        ]
        result = render(items, OutputFormat.JSON)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "a.tif"
        assert parsed[1]["name"] == "b.tif"

    def test_nested_model(self) -> None:
        info = NestedInfo(title="test", metadata={"key": "value"})
        result = render(info, OutputFormat.JSON)
        parsed = json.loads(result)
        assert parsed["metadata"]["key"] == "value"

    def test_null_fields(self) -> None:
        info = SampleInfo(name="x.tif", size=0)
        result = render(info, OutputFormat.JSON)
        parsed = json.loads(result)
        assert parsed["crs"] is None

    def test_valid_json(self) -> None:
        """Output must always be valid JSON — this is the structured output contract."""
        info = SampleInfo(name='special "chars".tif', size=0, tags=["a", "b"])
        result = render(info, OutputFormat.JSON)
        parsed = json.loads(result)  # must not raise
        assert parsed["name"] == 'special "chars".tif'


# ---------------------------------------------------------------------------
# CSV rendering
# ---------------------------------------------------------------------------


class TestCsvRendering:
    """Tests for CSV output."""

    def test_header_row(self) -> None:
        info = SampleInfo(name="test.tif", size=1024)
        result = render(info, OutputFormat.CSV)
        lines = result.strip().splitlines()
        assert lines[0].strip() == "name,size,crs,tags"

    def test_data_row(self) -> None:
        info = SampleInfo(name="test.tif", size=1024, crs="EPSG:4326")
        result = render(info, OutputFormat.CSV)
        lines = result.strip().splitlines()
        assert "test.tif" in lines[1]
        assert "1024" in lines[1]

    def test_multiple_rows(self) -> None:
        items = [
            SampleInfo(name="a.tif", size=100),
            SampleInfo(name="b.tif", size=200),
        ]
        result = render(items, OutputFormat.CSV)
        lines = result.strip().splitlines()
        assert len(lines) == 3  # header + 2 data rows

    def test_nested_as_json_string(self) -> None:
        info = SampleInfo(name="x.tif", size=0, tags=["a", "b"])
        result = render(info, OutputFormat.CSV)
        # CSV wraps the JSON in quotes and escapes internal quotes by doubling
        assert "a" in result and "b" in result


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


class TestTableRendering:
    """Tests for Rich table output."""

    def test_contains_values(self) -> None:
        info = SampleInfo(name="test.tif", size=1024, crs="EPSG:4326")
        result = render(info, OutputFormat.TABLE)
        assert "test.tif" in result
        assert "1024" in result
        assert "EPSG:4326" in result

    def test_null_shows_dash(self) -> None:
        info = SampleInfo(name="x.tif", size=0)
        result = render(info, OutputFormat.TABLE)
        assert "—" in result  # em dash for None values

    def test_multiple_items(self) -> None:
        items = [
            SampleInfo(name="a.tif", size=100),
            SampleInfo(name="b.tif", size=200),
        ]
        result = render(items, OutputFormat.TABLE)
        assert "a.tif" in result
        assert "b.tif" in result


# ---------------------------------------------------------------------------
# Quiet rendering
# ---------------------------------------------------------------------------


class TestQuietRendering:
    """Tests for quiet output."""

    def test_returns_empty(self) -> None:
        info = SampleInfo(name="test.tif", size=0)
        result = render(info, OutputFormat.QUIET)
        assert result == ""


# ---------------------------------------------------------------------------
# render_to_console
# ---------------------------------------------------------------------------


class TestRenderToConsole:
    """Tests for console output (smoke tests — actual rendering tested above)."""

    def test_json_does_not_raise(self, capsys: pytest.CaptureFixture[str]) -> None:
        info = SampleInfo(name="test.tif", size=0)
        render_to_console(info, OutputFormat.JSON)
        captured = capsys.readouterr()
        assert "test.tif" in captured.out

    def test_quiet_produces_no_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        info = SampleInfo(name="test.tif", size=0)
        render_to_console(info, OutputFormat.QUIET)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_color_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        info = SampleInfo(name="test.tif", size=0)
        render_to_console(info, OutputFormat.TABLE, no_color=True)
        # Should not raise; exact output depends on terminal
