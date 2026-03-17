"""Safe arithmetic expression evaluator for band math and formulas.

Parses mathematical expressions using Python's AST module and evaluates
them against a provided variable environment.  Only whitelisted operations
are permitted — no ``eval()``, ``exec()``, attribute access, subscripts,
or arbitrary function calls.

Supported constructs:

- **Arithmetic**: ``+``, ``-``, ``*``, ``/``, ``**``
- **Unary**: ``-x``, ``+x``
- **Comparison**: ``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=``
- **Safe functions**: ``clip``, ``where``, ``abs``, ``sqrt``, ``log``,
  ``minimum``, ``maximum``
- **Constants**: numeric literals (int, float)
- **Variables**: names bound in the environment dict

This module is shared infrastructure — domain packages (raster, pipeline)
import from here rather than implementing their own expression parsers.

Usage::

    from earthforge.core.expression import safe_eval

    env = {"B04": red_array, "B08": nir_array}
    ndvi = safe_eval("(B08 - B04) / (B08 + B04)", env)
"""

from __future__ import annotations

import ast
import operator
from typing import Any

# ---------------------------------------------------------------------------
# Operator whitelist
# ---------------------------------------------------------------------------

_BIN_OPS: dict[type[Any], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[Any], Any] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_CMP_OPS: dict[type[Any], Any] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

# ---------------------------------------------------------------------------
# Safe function whitelist
# ---------------------------------------------------------------------------


def _get_safe_functions() -> dict[str, Any]:
    """Build the safe function lookup table.

    Uses numpy when available (for array operations), falls back to
    stdlib ``math`` for scalar operations.

    Returns:
        Mapping of function name to callable.
    """
    funcs: dict[str, Any] = {}

    try:
        import numpy as np

        funcs["abs"] = np.abs
        funcs["sqrt"] = np.sqrt
        funcs["log"] = np.log
        funcs["clip"] = np.clip
        funcs["where"] = np.where
        funcs["minimum"] = np.minimum
        funcs["maximum"] = np.maximum
    except ImportError:
        import math

        funcs["abs"] = abs
        funcs["sqrt"] = math.sqrt
        funcs["log"] = math.log

    return funcs


_SAFE_FUNCTIONS = _get_safe_functions()


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


def safe_eval(expr_str: str, env: dict[str, Any]) -> Any:
    """Evaluate a mathematical expression safely via AST walking.

    Only arithmetic operators, comparisons, whitelisted function calls,
    numeric constants, and names present in ``env`` are permitted.  No
    builtins, attribute access, subscripts, or arbitrary code execution.

    Parameters:
        expr_str: Expression string (e.g. ``"(B08 - B04) / (B08 + B04)"``).
        env: Variable bindings (name → value, typically numpy arrays).

    Returns:
        Result of evaluating the expression.

    Raises:
        ValueError: If the expression contains unsupported constructs or
            references undefined variables.
    """

    def _eval(node: ast.expr) -> Any:
        # Numeric constant
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                msg = f"Unsupported constant type: {type(node.value).__name__}"
                raise ValueError(msg)
            return node.value

        # Variable reference
        if isinstance(node, ast.Name):
            if node.id in _SAFE_FUNCTIONS:
                return _SAFE_FUNCTIONS[node.id]
            if node.id not in env:
                msg = f"Unknown variable '{node.id}' in expression"
                raise ValueError(msg)
            return env[node.id]

        # Binary operation: a + b, a * b, etc.
        if isinstance(node, ast.BinOp):
            op_fn = _BIN_OPS.get(type(node.op))
            if op_fn is None:
                msg = f"Unsupported operator: {type(node.op).__name__}"
                raise ValueError(msg)
            return op_fn(_eval(node.left), _eval(node.right))

        # Unary operation: -x, +x
        if isinstance(node, ast.UnaryOp):
            op_fn = _UNARY_OPS.get(type(node.op))
            if op_fn is None:
                msg = f"Unsupported unary operator: {type(node.op).__name__}"
                raise ValueError(msg)
            return op_fn(_eval(node.operand))

        # Comparison: a < b, a >= b, etc.
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                msg = "Chained comparisons not supported"
                raise ValueError(msg)
            op_fn = _CMP_OPS.get(type(node.ops[0]))
            if op_fn is None:
                msg = f"Unsupported comparison: {type(node.ops[0]).__name__}"
                raise ValueError(msg)
            return op_fn(_eval(node.left), _eval(node.comparators[0]))

        # Function call: clip(x, 0, 1), sqrt(x), etc.
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                msg = "Only simple function calls are allowed (no methods or attribute access)"
                raise ValueError(msg)
            func_name = node.func.id
            if func_name not in _SAFE_FUNCTIONS:
                allowed = ', '.join(sorted(_SAFE_FUNCTIONS))
                msg = f"Unknown function '{func_name}'. Allowed: {allowed}"
                raise ValueError(msg)
            args = [_eval(arg) for arg in node.args]
            return _SAFE_FUNCTIONS[func_name](*args)

        msg = f"Unsupported expression node: {type(node).__name__}"
        raise ValueError(msg)

    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError as exc:
        msg = f"Invalid expression syntax: {exc}"
        raise ValueError(msg) from exc

    return _eval(tree.body)


def extract_variables(expr_str: str) -> set[str]:
    """Extract variable names referenced in an expression.

    Parameters:
        expr_str: Expression string.

    Returns:
        Set of variable names (excluding safe function names).

    Raises:
        ValueError: If the expression has invalid syntax.
    """
    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError as exc:
        msg = f"Invalid expression syntax: {exc}"
        raise ValueError(msg) from exc

    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in _SAFE_FUNCTIONS
    }
