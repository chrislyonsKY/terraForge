"""Tests for the EarthForge output rendering module."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from earthforge.core.output import (
    OutputFormat,
    StatusMarker,
    format_status,
    render,
    render_to_console,
)

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

    def test_high_contrast_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        info = SampleInfo(name="test.tif", size=0)
        render_to_console(info, OutputFormat.TABLE, high_contrast=True)
        # Should not raise; high-contrast uses bold white headers


# ---------------------------------------------------------------------------
# StatusMarker
# ---------------------------------------------------------------------------


class TestStatusMarker:
    """Tests for the StatusMarker enum and format_status helper."""

    def test_marker_values(self) -> None:
        assert StatusMarker.PASS == "[PASS]"  # noqa: S105
        assert StatusMarker.FAIL == "[FAIL]"
        assert StatusMarker.WARN == "[WARN]"
        assert StatusMarker.INFO == "[INFO]"
        assert StatusMarker.SKIP == "[SKIP]"

    def test_format_status_with_message(self) -> None:
        result = format_status(StatusMarker.PASS, "All checks passed")
        assert result == "[PASS] All checks passed"

    def test_format_status_without_message(self) -> None:
        result = format_status(StatusMarker.FAIL)
        assert result == "[FAIL]"

    def test_format_status_warn(self) -> None:
        result = format_status(StatusMarker.WARN, "Missing overviews")
        assert result == "[WARN] Missing overviews"


# ---------------------------------------------------------------------------
# FORCE_COLOR / NO_COLOR interaction
# ---------------------------------------------------------------------------


class TestColorEnvironment:
    """Tests for NO_COLOR and FORCE_COLOR environment variable handling."""

    def test_no_color_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        from earthforge.core.output import _should_use_color

        assert _should_use_color() is False

    def test_force_color_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        from earthforge.core.output import _should_use_color

        assert _should_use_color() is True

    def test_no_color_wins_over_force_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("FORCE_COLOR", "1")
        from earthforge.core.output import _should_use_color

        assert _should_use_color() is False

    def test_default_uses_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        from earthforge.core.output import _should_use_color

        assert _should_use_color() is True

    def test_force_no_color_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        from earthforge.core.output import _should_use_color

        assert _should_use_color(force_no_color=True) is False


# ---------------------------------------------------------------------------
# High-contrast rendering
# ---------------------------------------------------------------------------


class TestHighContrastRendering:
    """Tests for high-contrast mode in table rendering."""

    def test_render_high_contrast_contains_values(self) -> None:
        info = SampleInfo(name="test.tif", size=1024, crs="EPSG:4326")
        result = render(info, OutputFormat.TABLE, high_contrast=True)
        assert "test.tif" in result
        assert "1024" in result

    def test_render_high_contrast_json_unaffected(self) -> None:
        info = SampleInfo(name="test.tif", size=0)
        normal = render(info, OutputFormat.JSON)
        hc = render(info, OutputFormat.JSON, high_contrast=True)
        assert normal == hc
