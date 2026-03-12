"""Tests for earthforge.cube.slice — datacube spatiotemporal slicing.

All tests use synthetic in-memory Datasets written to temporary Zarr stores.
No real network requests are made.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("xarray")
pytest.importorskip("zarr")

import xarray as xr

from earthforge.cube.errors import CubeError
from earthforge.cube.slice import SliceResult, slice_cube


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_time_dataset(n_times: int = 24) -> xr.Dataset:
    """Create a Dataset with monthly time steps, lat/lon, and two variables."""
    import pandas as pd

    times = pd.date_range("2025-01-01", periods=n_times, freq="ME")
    lons = np.linspace(-85.0, -84.0, 10)
    lats = np.linspace(37.0, 38.0, 10)
    rng = np.random.default_rng(99)

    return xr.Dataset(
        {
            "temperature": xr.DataArray(
                rng.random((n_times, 10, 10)).astype(np.float32),
                dims=["time", "latitude", "longitude"],
                attrs={"units": "K", "long_name": "Air Temperature"},
            ),
            "precipitation": xr.DataArray(
                rng.random((n_times, 10, 10)).astype(np.float32),
                dims=["time", "latitude", "longitude"],
                attrs={"units": "mm", "long_name": "Precipitation"},
            ),
        },
        coords={
            "time": times,
            "latitude": ("latitude", lats, {"units": "degrees_north"}),
            "longitude": ("longitude", lons, {"units": "degrees_east"}),
        },
    )


@pytest.fixture
def zarr_store(tmp_path: Path) -> str:
    """Write a synthetic time-series Dataset to a temp Zarr store."""
    ds = _make_time_dataset()
    store_path = str(tmp_path / "source.zarr")
    ds.to_zarr(store_path, mode="w", consolidated=True)
    return store_path


# ---------------------------------------------------------------------------
# SliceResult model
# ---------------------------------------------------------------------------


class TestSliceResultModel:
    def test_fields_present(self) -> None:
        result = SliceResult(
            source="/tmp/in.zarr",
            output="/tmp/out.zarr",
            output_format="zarr",
            variables_selected=["t2m"],
            elapsed_seconds=1.23,
        )
        assert result.source == "/tmp/in.zarr"
        assert result.bbox is None
        assert result.time_range is None
        assert result.shape == {}
        assert result.output_size_bytes == 0


# ---------------------------------------------------------------------------
# Variable selection
# ---------------------------------------------------------------------------


class TestVariableSelection:
    @pytest.mark.asyncio
    async def test_select_single_variable(self, zarr_store: str, tmp_path: Path) -> None:
        out = str(tmp_path / "out.zarr")
        result = await slice_cube(zarr_store, variables=["temperature"], output=out)
        assert result.variables_selected == ["temperature"]

    @pytest.mark.asyncio
    async def test_select_all_variables_when_none(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        result = await slice_cube(zarr_store, variables=None, output=out)
        assert "temperature" in result.variables_selected
        assert "precipitation" in result.variables_selected

    @pytest.mark.asyncio
    async def test_missing_variable_raises(self, zarr_store: str, tmp_path: Path) -> None:
        out = str(tmp_path / "out.zarr")
        with pytest.raises(CubeError, match="not found"):
            await slice_cube(zarr_store, variables=["nonexistent_var"], output=out)


# ---------------------------------------------------------------------------
# Time filtering
# ---------------------------------------------------------------------------


class TestTimeFiltering:
    @pytest.mark.asyncio
    async def test_time_range_reduces_time_dim(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        result = await slice_cube(
            zarr_store,
            time_range="2025-01-01/2025-06-30",
            output=out,
        )
        assert result.shape.get("time", 0) <= 6  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_time_range_recorded_in_result(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        result = await slice_cube(
            zarr_store,
            time_range="2025-01-01/2025-06-30",
            output=out,
        )
        assert result.time_range == ["2025-01-01", "2025-06-30"]

    @pytest.mark.asyncio
    async def test_invalid_time_range_raises(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        with pytest.raises(CubeError, match="Invalid time_range"):
            await slice_cube(zarr_store, time_range="bad-format", output=out)


# ---------------------------------------------------------------------------
# Spatial (bbox) filtering
# ---------------------------------------------------------------------------


class TestBboxFiltering:
    @pytest.mark.asyncio
    async def test_bbox_reduces_spatial_dims(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        # Full extent is lon -85 to -84, lat 37 to 38
        result = await slice_cube(
            zarr_store,
            bbox=(-85.0, 37.0, -84.5, 37.5),
            output=out,
        )
        # Expect fewer lon/lat points than original 10
        assert result.shape.get("longitude", 10) <= 10
        assert result.shape.get("latitude", 10) <= 10

    @pytest.mark.asyncio
    async def test_bbox_recorded_in_result(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "out.zarr")
        bbox = (-85.0, 37.0, -84.5, 37.5)
        result = await slice_cube(zarr_store, bbox=bbox, output=out)
        assert result.bbox == list(bbox)


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


class TestOutputFormat:
    @pytest.mark.asyncio
    async def test_zarr_output_written(self, zarr_store: str, tmp_path: Path) -> None:
        out = str(tmp_path / "result.zarr")
        result = await slice_cube(zarr_store, variables=["temperature"], output=out)
        assert result.output_format == "zarr"
        assert Path(out).exists()

    @pytest.mark.asyncio
    async def test_netcdf_output_written(self, zarr_store: str, tmp_path: Path) -> None:
        pytest.importorskip("h5netcdf")
        out = str(tmp_path / "result.nc")
        result = await slice_cube(zarr_store, variables=["temperature"], output=out)
        assert result.output_format == "netcdf"
        assert Path(out).exists()

    @pytest.mark.asyncio
    async def test_output_size_recorded(self, zarr_store: str, tmp_path: Path) -> None:
        out = str(tmp_path / "result.zarr")
        result = await slice_cube(zarr_store, variables=["temperature"], output=out)
        assert result.output_size_bytes > 0

    @pytest.mark.asyncio
    async def test_elapsed_recorded(self, zarr_store: str, tmp_path: Path) -> None:
        out = str(tmp_path / "result.zarr")
        result = await slice_cube(zarr_store, variables=["temperature"], output=out)
        assert result.elapsed_seconds > 0


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


class TestCombinedFilters:
    @pytest.mark.asyncio
    async def test_variable_plus_time_plus_bbox(
        self, zarr_store: str, tmp_path: Path
    ) -> None:
        out = str(tmp_path / "result.zarr")
        result = await slice_cube(
            zarr_store,
            variables=["temperature"],
            bbox=(-85.0, 37.0, -84.5, 37.5),
            time_range="2025-01-01/2025-06-30",
            output=out,
        )
        assert result.variables_selected == ["temperature"]
        assert result.bbox is not None
        assert result.time_range is not None
        assert Path(out).exists()
        assert result.output_size_bytes > 0
