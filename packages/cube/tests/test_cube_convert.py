"""Tests for cube format conversion module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthforge.cube.convert import CubeConvertResult, convert_cube
from earthforge.cube.errors import CubeError


def _run(coro):
    return asyncio.run(coro)


def _create_netcdf(path: Path) -> None:
    ds = xr.Dataset(
        data_vars={"temp": (["time", "lat", "lon"], np.random.rand(3, 4, 5).astype(np.float32))},
        coords={
            "time": np.arange(3),
            "lat": np.linspace(-90, 90, 4),
            "lon": np.linspace(-180, 180, 5),
        },
    )
    ds.to_netcdf(str(path))


class TestNetCDFToZarr:
    def test_basic_conversion(self, tmp_path: Path) -> None:
        nc = tmp_path / "data.nc"
        _create_netcdf(nc)

        result = _run(convert_cube(str(nc), str(tmp_path / "data.zarr")))

        assert isinstance(result, CubeConvertResult)
        assert result.source_format == "netcdf"
        assert result.output_format == "zarr"
        assert "temp" in result.variables
        assert (tmp_path / "data.zarr").exists()

    def test_rechunked(self, tmp_path: Path) -> None:
        nc = tmp_path / "data.nc"
        _create_netcdf(nc)

        result = _run(convert_cube(str(nc), str(tmp_path / "data.zarr"), chunks={"time": 1}))

        assert result.chunks == {"time": 1}

        ds = xr.open_zarr(str(tmp_path / "data.zarr"))
        assert ds["temp"].chunks is not None
        ds.close()


class TestZarrToNetCDF:
    def test_basic_conversion(self, tmp_path: Path) -> None:
        zarr_path = tmp_path / "source.zarr"
        ds = xr.Dataset(
            data_vars={"precip": (["x", "y"], np.random.rand(3, 4).astype(np.float32))},
            coords={"x": np.arange(3), "y": np.arange(4)},
        )
        ds.to_zarr(str(zarr_path))

        result = _run(convert_cube(str(zarr_path), str(tmp_path / "out.nc")))

        assert result.output_format == "netcdf"
        assert (tmp_path / "out.nc").exists()

        ds_out = xr.open_dataset(str(tmp_path / "out.nc"))
        assert "precip" in ds_out
        ds_out.close()


class TestErrors:
    def test_nonexistent_source(self, tmp_path: Path) -> None:
        with pytest.raises(CubeError, match="Cannot open"):
            _run(convert_cube("/nonexistent.nc", str(tmp_path / "out.zarr")))
