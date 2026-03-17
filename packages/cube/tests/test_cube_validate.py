"""Tests for datacube validation module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthforge.cube.errors import CubeError
from earthforge.cube.validate import CubeValidationResult, validate_cube


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _create_cf_netcdf(path: Path) -> None:
    """Create a minimal CF-compliant NetCDF file."""
    ds = xr.Dataset(
        data_vars={
            "temperature": (
                ["time", "lat", "lon"],
                np.random.rand(3, 4, 5).astype(np.float32),
                {"units": "K", "long_name": "Air Temperature", "standard_name": "air_temperature"},
            ),
        },
        coords={
            "time": np.arange(3),
            "lat": np.linspace(-90, 90, 4),
            "lon": np.linspace(-180, 180, 5),
        },
        attrs={"Conventions": "CF-1.8"},
    )
    ds.to_netcdf(str(path))


def _create_minimal_netcdf(path: Path) -> None:
    """Create a minimal NetCDF without CF attributes."""
    ds = xr.Dataset(
        data_vars={
            "data": (["x", "y"], np.random.rand(3, 4).astype(np.float32)),
        },
        coords={
            "x": np.arange(3),
            "y": np.arange(4),
        },
    )
    ds.to_netcdf(str(path))


def _create_zarr(path: Path) -> None:
    """Create a minimal chunked Zarr store."""
    ds = xr.Dataset(
        data_vars={
            "precipitation": (
                ["time", "latitude", "longitude"],
                np.random.rand(10, 20, 30).astype(np.float32),
                {"units": "mm", "long_name": "Precipitation"},
            ),
        },
        coords={
            "time": np.arange(10),
            "latitude": np.linspace(-90, 90, 20),
            "longitude": np.linspace(-180, 180, 30),
        },
    )
    ds = ds.chunk({"time": 5, "latitude": 10, "longitude": 10})
    ds.to_zarr(str(path), consolidated=True)


class TestValidNetCDF:
    """Tests for valid NetCDF files."""

    def test_cf_compliant(self, tmp_path: Path) -> None:
        nc_path = tmp_path / "cf.nc"
        _create_cf_netcdf(nc_path)

        result = _run(validate_cube(str(nc_path)))

        assert isinstance(result, CubeValidationResult)
        assert result.is_valid is True
        assert result.format == "netcdf"
        assert "temperature" in result.variables
        assert "[PASS]" in result.summary

    def test_minimal_netcdf(self, tmp_path: Path) -> None:
        nc_path = tmp_path / "minimal.nc"
        _create_minimal_netcdf(nc_path)

        result = _run(validate_cube(str(nc_path)))

        assert result.is_valid is True
        assert len(result.dimensions) > 0


class TestValidZarr:
    """Tests for valid Zarr stores."""

    def test_chunked_zarr(self, tmp_path: Path) -> None:
        zarr_path = tmp_path / "store.zarr"
        _create_zarr(zarr_path)

        result = _run(validate_cube(str(zarr_path)))

        assert result.is_valid is True
        assert result.format == "zarr"
        assert "precipitation" in result.variables
        chunk_checks = [c for c in result.checks if c.check == "chunks"]
        assert any("[PASS]" in c.status for c in chunk_checks)


class TestInvalidCube:
    """Tests for invalid datacube files."""

    def test_nonexistent_file(self) -> None:
        with pytest.raises(CubeError, match="Cannot open"):
            _run(validate_cube("/nonexistent/cube.nc"))


class TestStatusMarkers:
    """Verify all check statuses include text markers."""

    def test_all_checks_have_text_markers(self, tmp_path: Path) -> None:
        nc_path = tmp_path / "markers.nc"
        _create_cf_netcdf(nc_path)

        result = _run(validate_cube(str(nc_path)))

        for check in result.checks:
            assert any(
                marker in check.status
                for marker in ["[PASS]", "[FAIL]", "[WARN]", "[INFO]", "[SKIP]"]
            ), f"Check '{check.check}' missing text marker: {check.status}"
