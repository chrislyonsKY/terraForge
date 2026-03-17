"""Tests for the safe expression evaluator."""

from __future__ import annotations

import pytest

from earthforge.core.expression import extract_variables, safe_eval


class TestBasicArithmetic:
    """Tests for basic arithmetic operations."""

    def test_addition(self) -> None:
        assert safe_eval("1 + 2", {}) == 3

    def test_subtraction(self) -> None:
        assert safe_eval("10 - 3", {}) == 7

    def test_multiplication(self) -> None:
        assert safe_eval("4 * 5", {}) == 20

    def test_division(self) -> None:
        assert safe_eval("10 / 4", {}) == 2.5

    def test_power(self) -> None:
        assert safe_eval("2 ** 3", {}) == 8

    def test_unary_neg(self) -> None:
        assert safe_eval("-5", {}) == -5

    def test_unary_pos(self) -> None:
        assert safe_eval("+5", {}) == 5

    def test_complex_expression(self) -> None:
        result = safe_eval("(10 - 4) / (10 + 4)", {})
        assert abs(result - 6 / 14) < 1e-10


class TestVariables:
    """Tests for variable substitution."""

    def test_simple_variable(self) -> None:
        assert safe_eval("x + 1", {"x": 5}) == 6

    def test_ndvi_formula(self) -> None:
        result = safe_eval("(B08 - B04) / (B08 + B04)", {"B08": 0.8, "B04": 0.2})
        assert abs(result - 0.6) < 1e-10

    def test_undefined_variable_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown variable"):
            safe_eval("x + y", {"x": 1})


class TestComparisons:
    """Tests for comparison operators."""

    def test_less_than(self) -> None:
        assert safe_eval("1 < 2", {}) is True

    def test_greater_equal(self) -> None:
        assert safe_eval("5 >= 5", {}) is True

    def test_not_equal(self) -> None:
        assert safe_eval("3 != 4", {}) is True

    def test_equality(self) -> None:
        assert safe_eval("2 == 2", {}) is True


class TestSafeFunctions:
    """Tests for whitelisted safe functions."""

    def test_abs(self) -> None:
        result = safe_eval("abs(-5)", {})
        assert result == 5

    def test_sqrt(self) -> None:
        result = safe_eval("sqrt(16)", {})
        assert abs(result - 4.0) < 1e-10

    def test_log(self) -> None:
        result = safe_eval("log(1)", {})
        assert abs(result - 0.0) < 1e-10

    def test_unknown_function_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown function"):
            safe_eval("exec('bad')", {})


class TestSafetyGuards:
    """Tests that unsafe constructs are rejected."""

    def test_attribute_access_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            safe_eval("x.__class__", {"x": 1})

    def test_string_constant_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported constant"):
            safe_eval("'hello'", {})

    def test_invalid_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid expression"):
            safe_eval("1 +", {})

    def test_import_rejected(self) -> None:
        with pytest.raises(ValueError):
            safe_eval("__import__('os')", {})


class TestExtractVariables:
    """Tests for the extract_variables helper."""

    def test_simple(self) -> None:
        assert extract_variables("x + y") == {"x", "y"}

    def test_ndvi(self) -> None:
        assert extract_variables("(B08 - B04) / (B08 + B04)") == {"B08", "B04"}

    def test_constants_only(self) -> None:
        assert extract_variables("1 + 2") == set()

    def test_excludes_functions(self) -> None:
        found = extract_variables("abs(x) + sqrt(y)")
        assert "abs" not in found
        assert "sqrt" not in found
        assert found == {"x", "y"}

    def test_invalid_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid expression"):
            extract_variables("1 +")


class TestNumpyIntegration:
    """Tests with numpy arrays (if available)."""

    def test_array_arithmetic(self) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        a = np.array([1.0, 2.0, 3.0])
        b = np.array([4.0, 5.0, 6.0])
        result = safe_eval("a + b", {"a": a, "b": b})
        np.testing.assert_array_equal(result, np.array([5.0, 7.0, 9.0]))

    def test_ndvi_arrays(self) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        nir = np.array([0.8, 0.6, 0.9])
        red = np.array([0.2, 0.3, 0.1])
        result = safe_eval("(B08 - B04) / (B08 + B04)", {"B08": nir, "B04": red})
        expected = (nir - red) / (nir + red)
        np.testing.assert_array_almost_equal(result, expected)

    def test_clip_function(self) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        a = np.array([-1.0, 0.5, 1.5])
        result = safe_eval("clip(a, 0, 1)", {"a": a})
        np.testing.assert_array_equal(result, np.array([0.0, 0.5, 1.0]))

    def test_where_function(self) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        a = np.array([1.0, -2.0, 3.0])
        result = safe_eval("where(a > 0, a, 0)", {"a": a})
        np.testing.assert_array_equal(result, np.array([1.0, 0.0, 3.0]))
