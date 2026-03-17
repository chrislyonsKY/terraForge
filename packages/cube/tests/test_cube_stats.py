"""Tests for cube statistics module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthforge.cube.errors import CubeError
from earthforge.cube.stats import CubeStatsResult, cube_stats


def _run(coro):
    return asyncio.run(coro)


def _create_cube(path: Path) -> None:
    """Create a simple NetCDF with known values."""
    data = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    ds = xr.Dataset(
        data_vars={
            "temperature": (
                ["time", "lat", "lon"],
                data,
                {"units": "K", "long_name": "Temperature"},
            ),
        },
        coords={
            "time": np.arange(2),
            "lat": np.linspace(-90, 90, 3),
            "lon": np.linspace(-180, 180, 4),
        },
    )
    ds.to_netcdf(str(path))


class TestCubeStats:
    def test_mean_over_time(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        result = _run(cube_stats(str(path), "temperature", reduce_dims=["time"]))

        assert isinstance(result, CubeStatsResult)
        assert result.operation == "mean"
        assert result.variable == "temperature"
        assert "time" in result.reduce_dims
        assert "lat" in result.remaining_dims
        assert "lon" in result.remaining_dims
        assert result.min >= 0

    def test_global_mean(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        result = _run(cube_stats(str(path), "temperature"))

        # All dims reduced, so remaining should be empty
        assert result.remaining_dims == []
        expected_mean = np.arange(24).mean()
        assert abs(result.mean - expected_mean) < 0.01

    def test_max_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        result = _run(cube_stats(str(path), "temperature", operation="max"))

        assert result.operation == "max"
        assert result.max == 23.0

    def test_save_output(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        result = _run(
            cube_stats(
                str(path),
                "temperature",
                reduce_dims=["time"],
                output=str(tmp_path / "mean.nc"),
            )
        )

        assert result.output is not None
        assert Path(result.output).exists()

        ds = xr.open_dataset(result.output)
        assert "temperature" in ds
        ds.close()


class TestErrors:
    def test_unknown_variable(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        with pytest.raises(CubeError, match="not found"):
            _run(cube_stats(str(path), "nonexistent"))

    def test_unknown_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        with pytest.raises(CubeError, match="Unknown operation"):
            _run(cube_stats(str(path), "temperature", operation="foobar"))

    def test_invalid_dimension(self, tmp_path: Path) -> None:
        path = tmp_path / "cube.nc"
        _create_cube(path)

        with pytest.raises(CubeError, match="not found"):
            _run(cube_stats(str(path), "temperature", reduce_dims=["depth"]))
