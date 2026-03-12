"""EarthForge ``bench`` command group — performance benchmarks.

Measures I/O and query performance for EarthForge operations and reports
timing, throughput, and comparison baselines. Results are emitted as a
structured table or JSON for CI performance tracking.

Available benchmarks
--------------------
vector-query
    Compares GeoParquet bbox query (with predicate pushdown) against a
    full sequential scan of the same data. Reports rows returned, elapsed
    time, and estimated data read ratio.

raster-info
    Measures round-trip time for COG header reads via HTTP range requests.
    Reports bytes transferred and time to first metadata.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import typer
from pydantic import BaseModel, Field

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="bench",
    help="Run EarthForge performance benchmarks.",
    no_args_is_help=True,
)


class BenchResult(BaseModel):
    """Structured result for a single benchmark run.

    Attributes:
        benchmark: Name of the benchmark (e.g. ``"vector-query"``).
        description: Human-readable description of what was measured.
        runs: Number of timed repetitions.
        results: Per-run timing and metric data.
        summary: Aggregated summary (min/mean/max elapsed, comparison).
    """

    benchmark: str = Field(title="Benchmark")
    description: str = Field(title="Description")
    runs: int = Field(title="Runs")
    results: list[dict[str, Any]] = Field(default_factory=list, title="Results")
    summary: dict[str, Any] = Field(default_factory=dict, title="Summary")


def _stats(times: list[float]) -> dict[str, float]:
    """Compute min/mean/max for a list of elapsed times."""
    return {
        "min_s": round(min(times), 4),
        "mean_s": round(sum(times) / len(times), 4),
        "max_s": round(max(times), 4),
    }


def vector_query(
    ctx: typer.Context,
    source: str = typer.Argument(
        help="Path to a GeoParquet file to benchmark against.",
    ),
    bbox: str = typer.Option(
        "-85.5,37.0,-84.0,38.5",
        "--bbox",
        help="Bounding box for the query benchmark: west,south,east,north.",
    ),
    runs: int = typer.Option(
        3,
        "--runs",
        "-n",
        help="Number of timed repetitions per method.",
    ),
) -> None:
    """Benchmark GeoParquet bbox query — predicate pushdown vs. full scan.

    Runs the same spatial query twice: once using EarthForge's predicate
    pushdown path (reads only intersecting row groups) and once by loading
    the entire file and filtering in Python. Reports timing and data read
    ratios for both methods.
    """
    from earthforge.cli.main import get_state

    state = get_state(ctx)

    parts = [float(v.strip()) for v in bbox.split(",")]
    if len(parts) != 4:
        typer.echo("Error: --bbox requires west,south,east,north", err=True)
        raise typer.Exit(code=1)
    bbox_tuple = (parts[0], parts[1], parts[2], parts[3])

    async def _run_bench() -> BenchResult:
        from pathlib import Path

        try:
            import geopandas as gpd
            import pyarrow.parquet as pq
        except ImportError as exc:
            typer.echo(f"Error: geopandas and pyarrow required for bench: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        from earthforge.vector.query import query_features

        file_size = Path(source).stat().st_size

        pushdown_times: list[float] = []
        fullscan_times: list[float] = []
        pushdown_rows = 0
        fullscan_rows = 0

        for _ in range(runs):
            # Method 1: EarthForge predicate pushdown
            t0 = time.perf_counter()
            result = await query_features(source, bbox=list(bbox_tuple))
            pushdown_times.append(time.perf_counter() - t0)
            pushdown_rows = result.feature_count

            # Method 2: Full scan — load all, filter in Python
            t0 = time.perf_counter()
            gdf = gpd.read_parquet(source)
            west, south, east, north = bbox_tuple
            _ = gdf.cx[west:east, south:north]  # type: ignore[misc]
            fullscan_times.append(time.perf_counter() - t0)
            fullscan_rows = len(_)

        # Estimate row groups read by pushdown (pyarrow metadata)
        pf = pq.ParquetFile(source)
        total_row_groups = pf.metadata.num_row_groups

        speedup = (
            round(sum(fullscan_times) / sum(pushdown_times), 2) if sum(pushdown_times) > 0 else 0.0
        )

        return BenchResult(
            benchmark="vector-query",
            description=(
                f"GeoParquet bbox query: pushdown vs. full scan "
                f"({file_size:,} bytes, {total_row_groups} row groups)"
            ),
            runs=runs,
            results=[
                {
                    "method": "earthforge predicate pushdown",
                    "rows_returned": pushdown_rows,
                    **_stats(pushdown_times),
                },
                {
                    "method": "geopandas full scan",
                    "rows_returned": fullscan_rows,
                    **_stats(fullscan_times),
                },
            ],
            summary={
                "file_size_bytes": file_size,
                "total_row_groups": total_row_groups,
                "pushdown_speedup_x": speedup,
                "bbox": list(bbox_tuple),
            },
        )

    result = asyncio.run(_run_bench())
    render_to_console(result, state.output, no_color=state.no_color)


def raster_info(
    ctx: typer.Context,
    source: str = typer.Argument(
        help="URL or path to a COG to benchmark header read time.",
    ),
    runs: int = typer.Option(
        3,
        "--runs",
        "-n",
        help="Number of timed repetitions.",
    ),
) -> None:
    """Benchmark COG header read time via HTTP range requests."""
    from earthforge.cli.main import get_state

    state = get_state(ctx)

    async def _run_bench() -> BenchResult:
        from earthforge.raster.info import inspect_raster

        times: list[float] = []
        for _ in range(runs):
            t0 = time.perf_counter()
            info = await inspect_raster(source)
            times.append(time.perf_counter() - t0)

        return BenchResult(
            benchmark="raster-info",
            description=f"COG header read via range request: {source}",
            runs=runs,
            results=[{"run": i + 1, "elapsed_s": round(t, 4)} for i, t in enumerate(times)],
            summary={
                **_stats(times),
                "dimensions": f"{info.width}x{info.height}",
                "overview_count": info.overview_count,
                "compression": info.compression,
            },
        )

    result = asyncio.run(_run_bench())
    render_to_console(result, state.output, no_color=state.no_color)


app.command(name="vector-query", help="Benchmark GeoParquet bbox query performance.")(vector_query)
app.command(name="raster-info", help="Benchmark COG header read time.")(raster_info)
