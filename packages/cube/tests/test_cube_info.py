"""Tests for earthforge.cube.info — datacube metadata inspection.

All tests use synthetic in-memory xarray Datasets written to temporary Zarr
or NetCDF stores. No real network requests are made.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("xarray")
pytest.importorskip("zarr")

import xarray as xr

from earthforge.cube.errors import CubeError
from earthforge.cube.info import (
    CubeInfo,
    DimensionInfo,
    VariableInfo,
    inspect_cube,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset(
    lon_range: tuple[float, float] = (-85.0, -84.0),
    lat_range: tuple[float, float] = (37.0, 38.0),
    n_times: int = 10,
    variables: list[str] | None = None,
) -> xr.Dataset:
    """Create a small synthetic Dataset with lon/lat/time coordinates."""
    if variables is None:
        variables = ["temperature", "precipitation"]

    lons = np.linspace(lon_range[0], lon_range[1], 8)
    lats = np.linspace(lat_range[0], lat_range[1], 8)
    times = np.arange(n_times)

    data_vars = {}
    for var in variables:
        data_vars[var] = xr.DataArray(
            np.random.default_rng(42).random((n_times, 8, 8)).astype(np.float32),
            dims=["time", "latitude", "longitude"],
            attrs={
                "units": "K" if var == "temperature" else "mm",
                "long_name": var.capitalize(),
                "standard_name": var,
            },
        )

    return xr.Dataset(
        data_vars,
        coords={
            "time": ("time", times),
            "latitude": ("latitude", lats, {"units": "degrees_north"}),
            "longitude": ("longitude", lons, {"units": "degrees_east"}),
        },
        attrs={"Conventions": "CF-1.8", "title": "Test dataset"},
    )


@pytest.fixture
def zarr_store(tmp_path: Path) -> str:
    """Write a synthetic Dataset to a temp Zarr store and return the path."""
    ds = _make_dataset()
    store_path = str(tmp_path / "test.zarr")
    ds.to_zarr(store_path, mode="w", consolidated=True)
    return store_path


@pytest.fixture
def netcdf_file(tmp_path: Path) -> str:
    """Write a synthetic Dataset to a temp NetCDF file and return the path."""
    pytest.importorskip("h5netcdf")
    ds = _make_dataset()
    nc_path = str(tmp_path / "test.nc")
    ds.to_netcdf(nc_path, engine="h5netcdf")
    return nc_path


# ---------------------------------------------------------------------------
# CubeInfo model
# ---------------------------------------------------------------------------


class TestCubeInfoModel:
    def test_fields_present(self) -> None:
        info = CubeInfo(
            source="/tmp/test.zarr",
            format="zarr",
            dimensions=[],
            variables=[],
        )
        assert info.source == "/tmp/test.zarr"
        assert info.format == "zarr"
        assert info.global_attrs == {}
        assert info.spatial_bbox is None
        assert info.time_range is None

    def test_serializes_to_json(self) -> None:
        info = CubeInfo(
            source="/tmp/test.zarr",
            format="zarr",
            dimensions=[DimensionInfo(name="time", size=10, dtype="int64")],
            variables=[
                VariableInfo(
                    name="t2m",
                    dims=["time"],
                    dtype="float32",
                    shape=[10],
                )
            ],
        )
        doc = json.loads(info.model_dump_json())
        assert doc["source"] == "/tmp/test.zarr"
        assert doc["dimensions"][0]["name"] == "time"
        assert doc["variables"][0]["name"] == "t2m"


# ---------------------------------------------------------------------------
# Zarr inspection
# ---------------------------------------------------------------------------


class TestInspectZarr:
    @pytest.mark.asyncio
    async def test_basic_zarr(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        assert info.format == "zarr"
        assert info.source == zarr_store

    @pytest.mark.asyncio
    async def test_dimensions_detected(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        dim_names = {d.name for d in info.dimensions}
        assert "latitude" in dim_names
        assert "longitude" in dim_names
        assert "time" in dim_names

    @pytest.mark.asyncio
    async def test_variables_detected(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        var_names = {v.name for v in info.variables}
        assert "temperature" in var_names
        assert "precipitation" in var_names

    @pytest.mark.asyncio
    async def test_variable_dtype(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        temp_var = next(v for v in info.variables if v.name == "temperature")
        assert "float32" in temp_var.dtype

    @pytest.mark.asyncio
    async def test_variable_shape(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        temp_var = next(v for v in info.variables if v.name == "temperature")
        assert temp_var.shape == [10, 8, 8]

    @pytest.mark.asyncio
    async def test_variable_dims(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        temp_var = next(v for v in info.variables if v.name == "temperature")
        assert temp_var.dims == ["time", "latitude", "longitude"]

    @pytest.mark.asyncio
    async def test_spatial_bbox_derived(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        assert info.spatial_bbox is not None
        west, south, east, north = info.spatial_bbox
        assert west == pytest.approx(-85.0, abs=0.1)
        assert east == pytest.approx(-84.0, abs=0.1)
        assert south == pytest.approx(37.0, abs=0.1)
        assert north == pytest.approx(38.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_global_attrs(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        assert info.global_attrs.get("Conventions") == "CF-1.8"
        assert info.global_attrs.get("title") == "Test dataset"

    @pytest.mark.asyncio
    async def test_dimension_units(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        lat_dim = next(d for d in info.dimensions if d.name == "latitude")
        assert lat_dim.units == "degrees_north"

    @pytest.mark.asyncio
    async def test_dimension_size(self, zarr_store: str) -> None:
        info = await inspect_cube(zarr_store)
        time_dim = next(d for d in info.dimensions if d.name == "time")
        assert time_dim.size == 10


# ---------------------------------------------------------------------------
# NetCDF inspection
# ---------------------------------------------------------------------------


class TestInspectNetCDF:
    @pytest.mark.asyncio
    async def test_basic_netcdf(self, netcdf_file: str) -> None:
        info = await inspect_cube(netcdf_file)
        assert info.format == "netcdf"

    @pytest.mark.asyncio
    async def test_variables_detected(self, netcdf_file: str) -> None:
        info = await inspect_cube(netcdf_file)
        var_names = {v.name for v in info.variables}
        assert "temperature" in var_names


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestInspectCubeErrors:
    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CubeError, match="Cannot"):
            await inspect_cube(str(tmp_path / "nonexistent.zarr"))

    @pytest.mark.asyncio
    async def test_non_cube_file_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.zarr"
        bad_file.write_text("not a zarr store")
        with pytest.raises(CubeError):
            await inspect_cube(str(bad_file))
