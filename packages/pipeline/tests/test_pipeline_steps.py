"""Tests for earthforge.pipeline.steps — step registry and built-in steps."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthforge.core.expression import safe_eval as _safe_eval
from earthforge.pipeline.errors import StepError
from earthforge.pipeline.steps import (
    StepContext,
    get_step,
    list_steps,
    register_step,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_builtin_steps_registered(self) -> None:
        steps = {s["name"] for s in list_steps()}
        assert "stac.fetch" in steps
        assert "raster.calc" in steps
        assert "raster.convert" in steps
        assert "vector.convert" in steps

    def test_get_known_step(self) -> None:
        fn = get_step("raster.calc")
        assert callable(fn)

    def test_get_unknown_step_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown pipeline step"):
            get_step("nonexistent.step")

    def test_register_custom_step(self) -> None:
        @register_step("test.custom_step_xyz")
        async def my_step(ctx: StepContext):
            """Custom test step."""

        assert get_step("test.custom_step_xyz") is my_step
        assert any(s["name"] == "test.custom_step_xyz" for s in list_steps())

    def test_list_steps_sorted(self) -> None:
        names = [s["name"] for s in list_steps()]
        assert names == sorted(names)

    def test_list_steps_has_descriptions(self) -> None:
        for step in list_steps():
            assert "name" in step
            assert "description" in step


# ---------------------------------------------------------------------------
# Safe expression evaluator
# ---------------------------------------------------------------------------


class TestSafeEval:
    def test_simple_arithmetic(self) -> None:
        assert _safe_eval("2 + 3", {}) == 5

    def test_variable_substitution(self) -> None:
        result = _safe_eval("a + b", {"a": 10, "b": 5})
        assert result == 15

    def test_ndvi_expression(self) -> None:
        import numpy as np

        nir = np.array([0.6, 0.8, 0.4], dtype=np.float32)
        red = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        result = _safe_eval("(B08 - B04) / (B08 + B04)", {"B08": nir, "B04": red})
        expected = (nir - red) / (nir + red)
        np.testing.assert_allclose(result, expected)

    def test_power_operator(self) -> None:
        assert _safe_eval("2 ** 10", {}) == 1024

    def test_unary_negation(self) -> None:
        assert _safe_eval("-x", {"x": 5}) == -5

    def test_unknown_variable_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown variable"):
            _safe_eval("x + y", {"x": 1})

    def test_safe_function_allowed(self) -> None:
        result = _safe_eval("abs(x)", {"x": -5})
        assert result == 5

    def test_unsafe_function_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown function"):
            _safe_eval("exec('bad')", {})

    def test_attribute_access_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expression node"):
            _safe_eval("x.shape", {"x": 1})

    def test_string_constant_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported constant type"):
            _safe_eval('"hello"', {})

    def test_invalid_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            _safe_eval("(a + b", {"a": 1, "b": 2})


# ---------------------------------------------------------------------------
# raster.calc step
# ---------------------------------------------------------------------------


class TestRasterCalcStep:
    @pytest.mark.asyncio
    async def test_missing_expression_raises(self, tmp_path: Path) -> None:
        ctx = StepContext(
            item_id="test_item",
            item_url="https://example.com/item",
            output_dir=tmp_path,
            params={},  # no expression
        )
        step_fn = get_step("raster.calc")
        with pytest.raises(StepError, match="Missing required param 'expression'"):
            await step_fn(ctx)

    @pytest.mark.asyncio
    async def test_missing_band_raises(self, tmp_path: Path) -> None:
        ctx = StepContext(
            item_id="test_item",
            item_url="https://example.com/item",
            output_dir=tmp_path,
            params={"expression": "(B08 - B04) / (B08 + B04)", "output": "ndvi.tif"},
            asset_paths={},  # no bands
        )
        step_fn = get_step("raster.calc")
        with pytest.raises(StepError, match="not in asset_paths"):
            await step_fn(ctx)

    @pytest.mark.asyncio
    async def test_computes_result(self, tmp_path: Path) -> None:
        """Full raster.calc execution with a synthetic GeoTIFF."""
        pytest.importorskip("rasterio")
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds

        def _write_band(path: Path, arr: np.ndarray) -> None:
            transform = from_bounds(-85, 37, -84, 38, arr.shape[1], arr.shape[0])
            with rasterio.open(
                str(path),
                "w",
                driver="GTiff",
                height=arr.shape[0],
                width=arr.shape[1],
                count=1,
                dtype=arr.dtype,
                crs="EPSG:4326",
                transform=transform,
            ) as dst:
                dst.write(arr, 1)

        b04 = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        b08 = np.array([[0.6, 0.7], [0.8, 0.9]], dtype=np.float32)

        b04_path = tmp_path / "B04.tif"
        b08_path = tmp_path / "B08.tif"
        _write_band(b04_path, b04)
        _write_band(b08_path, b08)

        ctx = StepContext(
            item_id="S2A_TEST",
            item_url="https://example.com/item",
            output_dir=tmp_path,
            params={
                "expression": "(B08 - B04) / (B08 + B04)",
                "output": "ndvi_{item_id}.tif",
            },
            asset_paths={"B04": str(b04_path), "B08": str(b08_path)},
        )

        step_fn = get_step("raster.calc")
        result = await step_fn(ctx)

        assert result.succeeded if hasattr(result, "succeeded") else True
        output_path = tmp_path / "ndvi_S2A_TEST.tif"
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        assert "result" in result.outputs


# ---------------------------------------------------------------------------
# raster.convert step
# ---------------------------------------------------------------------------


class TestRasterConvertStep:
    @pytest.mark.asyncio
    async def test_no_input_raises(self, tmp_path: Path) -> None:
        ctx = StepContext(
            item_id="test_item",
            item_url="https://example.com/item",
            output_dir=tmp_path,
            params={"format": "COG"},
            asset_paths={},  # nothing available
        )
        step_fn = get_step("raster.convert")
        with pytest.raises(StepError, match="No input found"):
            await step_fn(ctx)
