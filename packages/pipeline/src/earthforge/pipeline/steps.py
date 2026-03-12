"""EarthForge pipeline step registry and built-in step implementations.

Each step is an async callable with the signature::

    async def step_fn(ctx: StepContext) -> StepResult

Steps are registered by name (e.g. ``"raster.convert"``, ``"raster.calc"``)
and looked up by the pipeline runner when processing ``for_each_item`` blocks.

The ``StepContext`` carries the current STAC item, its downloaded asset paths,
the pipeline-level output directory, and the step's own parameters dict.

Built-in steps
--------------
stac.fetch
    Download STAC item assets.  ``assets`` param selects which keys to
    download; default downloads all non-thumbnail data assets.

raster.calc
    Evaluate a band math expression over GeoTIFF bands loaded via rasterio.
    The expression is parsed as a safe arithmetic AST — no ``eval`` or
    ``exec`` is used (per CLAUDE.md guardrail).

raster.convert
    Convert a GeoTIFF to COG using the GDAL COG driver via
    ``earthforge.raster.convert``.

vector.convert
    Convert a vector file to GeoParquet.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import operator
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from earthforge.pipeline.errors import StepError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step context and result
# ---------------------------------------------------------------------------


@dataclass
class StepContext:
    """Runtime context passed to each step during execution.

    Attributes:
        item_id: STAC item ID being processed.
        item_url: URL of the STAC item JSON.
        asset_paths: Mapping of asset key → local file path (populated by
            ``stac.fetch`` steps that run before other steps).
        output_dir: Per-item output directory (``<pipeline.output_dir>/<item_id>``).
        params: Step-specific parameter dict from the pipeline YAML.
        profile: EarthForge profile name (from the pipeline or global config).
    """

    item_id: str
    item_url: str
    asset_paths: dict[str, str] = field(default_factory=dict)
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    params: dict[str, Any] = field(default_factory=dict)
    profile: str = "default"


@dataclass
class StepResult:
    """Result from a single step execution.

    Attributes:
        step_name: Registered name of the step (e.g. ``"raster.calc"``).
        item_id: STAC item ID that was processed.
        outputs: Mapping of output key → file path (for downstream steps).
        elapsed_seconds: Wall-clock time for this step.
        skipped: True if the step was skipped (e.g. output already exists).
        message: Human-readable summary of what the step did.
    """

    step_name: str
    item_id: str
    outputs: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    skipped: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_step(name: str) -> Callable[..., Any]:
    """Decorator to register an async step function under ``name``.

    Parameters:
        name: Step name as it appears in the pipeline YAML
            (e.g. ``"raster.convert"``).

    Returns:
        The original function, unchanged.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY[name] = fn
        return fn

    return decorator


def get_step(name: str) -> Callable[..., Any]:
    """Look up a registered step by name.

    Parameters:
        name: Step name.

    Returns:
        The registered async step callable.

    Raises:
        KeyError: If the name is not registered.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            f"Unknown pipeline step '{name}'. Available steps: {available or '(none registered)'}"
        )
    return _REGISTRY[name]


def list_steps() -> list[dict[str, str]]:
    """Return a sorted list of all registered step names and their docstrings.

    Returns:
        List of dicts with ``name`` and ``description`` keys.
    """
    result = []
    for name, fn in sorted(_REGISTRY.items()):
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        result.append({"name": name, "description": doc})
    return result


# ---------------------------------------------------------------------------
# Built-in steps
# ---------------------------------------------------------------------------


@register_step("stac.fetch")
async def step_stac_fetch(ctx: StepContext) -> StepResult:
    """Download STAC item assets to the output directory.

    Parameters (``ctx.params``):
        assets: List of asset keys to download. Default: all data assets.
        parallel: Max concurrent downloads. Default: 4.
    """
    t0 = time.perf_counter()

    try:
        from earthforge.core.config import EarthForgeProfile
        from earthforge.stac.fetch import fetch_assets
    except ImportError as exc:
        raise StepError(
            "stac.fetch", ctx.item_id, f"earthforge-stac not installed: {exc}"
        ) from exc

    profile = EarthForgeProfile(name=ctx.profile, storage_backend="local")
    assets: list[str] | None = ctx.params.get("assets")
    parallel: int = int(ctx.params.get("parallel", 4))

    try:
        result = await fetch_assets(
            profile,
            item_url=ctx.item_url,
            output_dir=str(ctx.output_dir),
            assets=assets,
            parallel=parallel,
        )
    except Exception as exc:
        raise StepError("stac.fetch", ctx.item_id, str(exc)) from exc

    # Populate asset_paths for downstream steps
    for af in result.files:
        if af.local_path:
            ctx.asset_paths[af.key] = af.local_path

    outputs = {af.key: af.local_path for af in result.files if af.local_path}
    msg = (
        f"Fetched {result.assets_fetched} assets, "
        f"skipped {result.assets_skipped} "
        f"({result.total_bytes_downloaded:,} bytes in {result.elapsed_seconds:.2f}s)"
    )

    return StepResult(
        step_name="stac.fetch",
        item_id=ctx.item_id,
        outputs=outputs,
        elapsed_seconds=time.perf_counter() - t0,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Safe expression evaluator for raster.calc
# ---------------------------------------------------------------------------

_SAFE_OPS: dict[type[Any], Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr_str: str, env: dict[str, Any]) -> Any:
    """Evaluate a band math expression using a safe AST walker.

    Only arithmetic operators (+, -, *, /, **) and names present in ``env``
    are permitted. No builtins, attribute access, subscripts, or function
    calls are allowed. This prevents arbitrary code execution without
    resorting to ``eval()`` or ``exec()``.

    Parameters:
        expr_str: Band math expression string (e.g. ``"(B08 - B04) / (B08 + B04)"``).
        env: Variable bindings (band name → array).

    Returns:
        Result of evaluating the expression.

    Raises:
        ValueError: If the expression contains unsupported constructs.
    """

    def _eval(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError(f"Unsupported constant type: {type(node.value)}")
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(f"Unknown variable '{node.id}' in expression")
            return env[node.id]
        if isinstance(node, ast.BinOp):
            op_type: type[Any] = type(node.op)
            if op_type not in _SAFE_OPS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            return _SAFE_OPS[op_type](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _SAFE_OPS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            return _SAFE_OPS[op_type](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    return _eval(tree.body)


@register_step("raster.calc")
async def step_raster_calc(ctx: StepContext) -> StepResult:
    """Evaluate a band math expression over GeoTIFF bands.

    Parameters (``ctx.params``):
        expression: Band math expression (e.g. ``"(B08 - B04) / (B08 + B04)"``).
            Variable names must match asset keys in ``ctx.asset_paths``.
        output: Output filename template. ``{item_id}`` is replaced with
            the STAC item ID.
        dtype: Output dtype (default: ``float32``).
    """
    t0 = time.perf_counter()

    expression: str = ctx.params.get("expression", "")
    output_tmpl: str = ctx.params.get("output", "calc_{item_id}.tif")
    dtype: str = ctx.params.get("dtype", "float32")

    if not expression:
        raise StepError("raster.calc", ctx.item_id, "Missing required param 'expression'")

    output_name = output_tmpl.replace("{item_id}", ctx.item_id)
    output_path = ctx.output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()

    def _run_calc() -> None:
        try:
            import numpy as np
            import rasterio
        except ImportError as exc:
            raise StepError(
                "raster.calc", ctx.item_id, f"rasterio/numpy not installed: {exc}"
            ) from exc

        # Load all referenced bands into env
        env: dict[str, Any] = {}
        profile_out: dict[str, Any] = {}

        # Parse expression AST to find referenced names
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise StepError("raster.calc", ctx.item_id, f"Invalid expression: {exc}") from exc

        needed = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

        for band_key in needed:
            path = ctx.asset_paths.get(band_key)
            if not path:
                raise StepError(
                    "raster.calc",
                    ctx.item_id,
                    f"Band '{band_key}' not in asset_paths. Available: {list(ctx.asset_paths)}",
                )
            with rasterio.open(path) as src:
                arr = src.read(1).astype(np.float32)
                env[band_key] = arr
                if not profile_out:
                    profile_out = src.profile.copy()

        # Evaluate expression safely
        result_arr = _safe_eval(expression, env)
        result_arr = result_arr.astype(dtype)

        profile_out.update(
            dtype=dtype,
            count=1,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        with rasterio.open(str(output_path), "w", **profile_out) as dst:
            dst.write(result_arr, 1)

    try:
        await loop.run_in_executor(None, _run_calc)
    except StepError:
        raise
    except Exception as exc:
        raise StepError("raster.calc", ctx.item_id, str(exc)) from exc

    return StepResult(
        step_name="raster.calc",
        item_id=ctx.item_id,
        outputs={"result": str(output_path)},
        elapsed_seconds=time.perf_counter() - t0,
        message=f"Computed '{expression}' → {output_path.name}",
    )


@register_step("raster.convert")
async def step_raster_convert(ctx: StepContext) -> StepResult:
    """Convert a raster to COG or another format.

    Parameters (``ctx.params``):
        format: Target format — ``"COG"`` (default) or ``"GeoTIFF"``.
        compression: COG compression — ``"deflate"`` (default), ``"lzw"``, ``"zstd"``.
        input: Asset key to convert (default: ``"result"`` from prior step,
            or the first asset path if only one exists).
        output: Output filename template. ``{item_id}`` is replaced.
    """
    t0 = time.perf_counter()

    fmt: str = ctx.params.get("format", "COG").upper()
    compression: str = ctx.params.get("compression", "deflate")
    input_key: str = ctx.params.get("input", "result")
    output_tmpl: str = ctx.params.get("output", "{item_id}_cog.tif")

    output_name = output_tmpl.replace("{item_id}", ctx.item_id)
    output_path = ctx.output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve input
    source_path = ctx.asset_paths.get(input_key)
    if not source_path and ctx.asset_paths:
        # Fall back to first available asset
        source_path = next(iter(ctx.asset_paths.values()))
    if not source_path:
        raise StepError(
            "raster.convert",
            ctx.item_id,
            f"No input found for key '{input_key}'. "
            f"Available asset_paths: {list(ctx.asset_paths)}",
        )

    try:
        from earthforge.raster.convert import convert_to_cog
    except ImportError as exc:
        raise StepError(
            "raster.convert", ctx.item_id, f"earthforge-raster not installed: {exc}"
        ) from exc

    try:
        result = await convert_to_cog(
            source=source_path,
            output=str(output_path),
            compression=compression,
        )
    except Exception as exc:
        raise StepError("raster.convert", ctx.item_id, str(exc)) from exc

    ctx.asset_paths["cog"] = str(output_path)

    return StepResult(
        step_name="raster.convert",
        item_id=ctx.item_id,
        outputs={"cog": str(output_path)},
        elapsed_seconds=time.perf_counter() - t0,
        message=(
            f"Converted to {fmt} ({compression}) → "
            f"{output_path.name} ({result.file_size_bytes:,} bytes)"
        ),
    )


@register_step("vector.convert")
async def step_vector_convert(ctx: StepContext) -> StepResult:
    """Convert a vector file to GeoParquet.

    Parameters (``ctx.params``):
        input: Asset key to convert.
        output: Output filename template. ``{item_id}`` is replaced.
    """
    t0 = time.perf_counter()

    input_key: str = ctx.params.get("input", "data")
    output_tmpl: str = ctx.params.get("output", "{item_id}.parquet")

    output_name = output_tmpl.replace("{item_id}", ctx.item_id)
    output_path = ctx.output_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_path = ctx.asset_paths.get(input_key)
    if not source_path:
        raise StepError(
            "vector.convert",
            ctx.item_id,
            f"No input for key '{input_key}'. Available: {list(ctx.asset_paths)}",
        )

    try:
        from earthforge.vector.convert import convert_vector
    except ImportError as exc:
        raise StepError(
            "vector.convert", ctx.item_id, f"earthforge-vector not installed: {exc}"
        ) from exc

    try:
        result = await convert_vector(source=source_path, output=str(output_path))
    except Exception as exc:
        raise StepError("vector.convert", ctx.item_id, str(exc)) from exc

    return StepResult(
        step_name="vector.convert",
        item_id=ctx.item_id,
        outputs={"parquet": str(output_path)},
        elapsed_seconds=time.perf_counter() - t0,
        message=(
            f"Converted to GeoParquet → {output_path.name} ({result.feature_count:,} features)"
        ),
    )
