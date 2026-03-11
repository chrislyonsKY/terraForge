"""Tests for the EarthForge CLI main app."""

from __future__ import annotations

from typer.testing import CliRunner

from earthforge.cli.main import app
from earthforge.core import __version__

runner = CliRunner()


class TestRootApp:
    """Tests for the root CLI application."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "earthforge" in result.output.lower() or "cloud-native" in result.output.lower()

    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # Typer returns exit code 0 or 2 for no_args_is_help depending on version
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output or "usage" in result.output


class TestInfoCommand:
    """Tests for the info subcommand."""

    def test_info_help(self) -> None:
        result = runner.invoke(app, ["info", "--help"])
        assert result.exit_code == 0
        assert "source" in result.output.lower() or "path" in result.output.lower()

    def test_info_geotiff(self, tmp_path: object) -> None:
        """Detect a GeoTIFF from a real temp file with TIFF magic bytes."""
        from pathlib import Path

        p = Path(str(tmp_path)) / "test.tif"
        p.write_bytes(b"\x49\x49\x2a\x00" + b"\x00" * 508)

        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 0
        assert "geotiff" in result.output.lower() or "GeoTIFF" in result.output

    def test_info_cog(self, tmp_path: object) -> None:
        """Detect a COG from a TIFF with tile width tags."""
        from pathlib import Path

        p = Path(str(tmp_path)) / "tiled.tif"
        header = bytearray(512)
        header[0:4] = b"\x49\x49\x2a\x00"
        header[30:32] = b"\x42\x01"  # TileWidth tag
        p.write_bytes(bytes(header))

        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 0
        assert "cog" in result.output.lower() or "COG" in result.output

    def test_info_parquet(self, tmp_path: object) -> None:
        """Detect a Parquet file."""
        from pathlib import Path

        p = Path(str(tmp_path)) / "data.parquet"
        p.write_bytes(b"PAR1" + b"\x00" * 508)

        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 0
        assert "parquet" in result.output.lower()

    def test_info_json_output(self, tmp_path: object) -> None:
        """--output json produces valid JSON."""
        import json
        from pathlib import Path

        p = Path(str(tmp_path)) / "test.tif"
        p.write_bytes(b"\x49\x49\x2a\x00" + b"\x00" * 508)

        result = runner.invoke(app, ["--output", "json", "info", str(p)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["format"] == "geotiff"
        assert parsed["source"] == str(p)
        assert isinstance(parsed["size_bytes"], int)

    def test_info_csv_output(self, tmp_path: object) -> None:
        """--output csv produces CSV with header."""
        from pathlib import Path

        p = Path(str(tmp_path)) / "test.fgb"
        p.write_bytes(b"fgb\x03" + b"\x00" * 508)

        result = runner.invoke(app, ["--output", "csv", "info", str(p)])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) >= 2  # header + data
        assert "source" in lines[0]

    def test_info_quiet_output(self, tmp_path: object) -> None:
        """--output quiet produces no output."""
        from pathlib import Path

        p = Path(str(tmp_path)) / "test.tif"
        p.write_bytes(b"\x49\x49\x2a\x00" + b"\x00" * 508)

        result = runner.invoke(app, ["--output", "quiet", "info", str(p)])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_info_nonexistent_file(self) -> None:
        """Nonexistent file should exit with error."""
        result = runner.invoke(app, ["info", "/nonexistent/path.tif"])
        assert result.exit_code != 0
