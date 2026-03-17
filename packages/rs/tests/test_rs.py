"""Tests for the EarthForge Rust acceleration extension.

These tests verify both the Rust-accelerated path (when earthforge-rs is
installed) and the pure-Python fallback path (when it is not). CI must run
these tests in BOTH configurations to ensure the fallback stays functional.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import guards — detect whether Rust extension is available
# ---------------------------------------------------------------------------

try:
    import earthforge_rs

    HAS_RS = True
except ImportError:
    HAS_RS = False

rs_only = pytest.mark.skipif(not HAS_RS, reason="earthforge-rs not installed")
fallback_only = pytest.mark.skipif(HAS_RS, reason="earthforge-rs is installed; testing fallback")


# ---------------------------------------------------------------------------
# Format detection tests
# ---------------------------------------------------------------------------


class TestFormatDetection:
    """Tests for detect_format_batch (Rust) and Python fallback."""

    def _detect_batch(self, paths: list[str]) -> list[str]:
        """Use Rust if available, otherwise fall back to Python."""
        if HAS_RS:
            return earthforge_rs.detect_format_batch(paths)
        else:
            from earthforge.core.formats import detect_sync as detect

            results = []
            for p in paths:
                try:
                    result = detect(p)
                    results.append(result.value if hasattr(result, "value") else str(result))
                except Exception:
                    results.append("unknown")
            return results

    def test_tiff_magic(self, tmp_path: Path) -> None:
        tiff = tmp_path / "test.tif"
        tiff.write_bytes(b"II\x2a\x00" + b"\x00" * 100)

        results = self._detect_batch([str(tiff)])
        assert results[0] in ("geotiff", "tiff", "FormatType.GEOTIFF")

    def test_parquet_magic(self, tmp_path: Path) -> None:
        pq = tmp_path / "test.parquet"
        pq.write_bytes(b"PAR1" + b"\x00" * 100)

        results = self._detect_batch([str(pq)])
        assert "parquet" in results[0].lower()

    def test_unknown_magic(self, tmp_path: Path) -> None:
        unk = tmp_path / "test.bin"
        unk.write_bytes(b"UNKNOWN_FORMAT_BYTES")

        results = self._detect_batch([str(unk)])
        assert results[0] == "unknown"

    def test_batch_multiple(self, tmp_path: Path) -> None:
        tiff = tmp_path / "a.tif"
        tiff.write_bytes(b"II\x2a\x00" + b"\x00" * 100)

        pq = tmp_path / "b.parquet"
        pq.write_bytes(b"PAR1" + b"\x00" * 100)

        results = self._detect_batch([str(tiff), str(pq)])
        assert len(results) == 2

    def test_empty_batch(self) -> None:
        results = self._detect_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# Fallback import pattern tests
# ---------------------------------------------------------------------------


class TestFallbackPattern:
    """Verify the try/except import pattern works correctly."""

    def test_import_guard_does_not_crash(self) -> None:
        """The import guard must not raise regardless of whether Rust is installed."""
        try:
            from earthforge_rs import detect_format_batch

            assert callable(detect_format_batch)
        except ImportError:
            # Fallback: import the Python version
            from earthforge.core.formats import detect_sync as detect

            assert callable(detect)

    def test_format_detection_fallback(self, tmp_path: Path) -> None:
        """Python fallback for format detection must work."""
        from earthforge.core.formats import detect_sync as detect

        tiff = tmp_path / "test.tif"
        tiff.write_bytes(b"II\x2a\x00" + b"\x00" * 100)

        result = detect(str(tiff))
        # Should return some recognized format, not crash
        assert result is not None


# ---------------------------------------------------------------------------
# Rust-only tests (skipped when extension not installed)
# ---------------------------------------------------------------------------


@rs_only
class TestRustExtension:
    """Tests that only run when earthforge-rs is installed."""

    def test_module_has_expected_functions(self) -> None:
        assert hasattr(earthforge_rs, "detect_format_batch")
        assert hasattr(earthforge_rs, "parallel_range_read")
        assert hasattr(earthforge_rs, "read_geoparquet_fast")

    def test_detect_format_batch_returns_list(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"test data")

        result = earthforge_rs.detect_format_batch([str(f)])
        assert isinstance(result, list)
        assert len(result) == 1

    def test_read_geoparquet_fast_missing_file(self) -> None:
        with pytest.raises(RuntimeError):
            earthforge_rs.read_geoparquet_fast("/nonexistent/file.parquet")

    def test_read_geoparquet_fast_valid(self, tmp_path: Path) -> None:
        """Test with a real Parquet file created by pyarrow."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pytest.skip("pyarrow not installed")

        table = pa.table({"col": [1, 2, 3]})
        path = tmp_path / "test.parquet"
        pq.write_table(table, str(path))

        result = earthforge_rs.read_geoparquet_fast(str(path))
        assert result.num_rows == 3
