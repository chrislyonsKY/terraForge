"""EarthForge pipeline runner — YAML pipeline execution engine.

Loads a pipeline YAML document, validates it against the schema, fetches the
source STAC items, and executes the step graph. ``for_each_item`` blocks run
concurrently across items using ``asyncio.TaskGroup`` bounded by a semaphore.

Usage::

    from earthforge.pipeline.runner import run_pipeline, load_pipeline

    doc = load_pipeline("pipeline.yaml")
    result = await run_pipeline(doc)
    print(f"Processed {result.items_succeeded}/{result.items_total} items")
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from earthforge.pipeline.errors import PipelineError, PipelineValidationError, StepError
from earthforge.pipeline.schema import validate_pipeline_doc
from earthforge.pipeline.steps import StepContext, StepResult, get_step

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class ItemResult(BaseModel):
    """Execution result for a single STAC item.

    Attributes:
        item_id: STAC item ID.
        item_url: URL the item was fetched from.
        succeeded: True if all steps completed without error.
        steps: Per-step results.
        error: Error message if the item failed, otherwise None.
        elapsed_seconds: Wall-clock time for all steps on this item.
    """

    item_id: str = Field(title="Item ID")
    item_url: str = Field(title="Item URL")
    succeeded: bool = Field(title="Succeeded")
    steps: list[dict[str, Any]] = Field(default_factory=list, title="Steps")
    error: str | None = Field(default=None, title="Error")
    elapsed_seconds: float = Field(title="Elapsed (s)")


class PipelineRunResult(BaseModel):
    """Structured result for a complete pipeline run.

    Attributes:
        pipeline_name: Name field from the pipeline YAML.
        items_total: Total number of source items.
        items_succeeded: Items that completed all steps without error.
        items_failed: Items that encountered at least one step error.
        item_results: Per-item detailed results.
        elapsed_seconds: Total wall-clock time for the pipeline run.
    """

    pipeline_name: str = Field(title="Pipeline")
    items_total: int = Field(title="Total Items")
    items_succeeded: int = Field(title="Succeeded")
    items_failed: int = Field(title="Failed")
    item_results: list[ItemResult] = Field(default_factory=list, title="Item Results")
    elapsed_seconds: float = Field(title="Elapsed (s)")


# ---------------------------------------------------------------------------
# Pipeline document loading
# ---------------------------------------------------------------------------


def load_pipeline(path: str) -> dict[str, Any]:
    """Load and parse a pipeline YAML file.

    Parameters:
        path: Filesystem path to the pipeline YAML file.

    Returns:
        Parsed pipeline document as a Python dict.

    Raises:
        PipelineError: If the file cannot be read.
        PipelineValidationError: If the YAML is invalid or malformed.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Cannot read pipeline file '{path}': {exc}") from exc

    try:
        doc: dict[str, Any] = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PipelineValidationError(f"YAML parse error: {exc}") from exc

    if not isinstance(doc, dict):
        raise PipelineValidationError("Pipeline YAML must be a mapping at the top level")

    return doc


# ---------------------------------------------------------------------------
# Source: STAC search
# ---------------------------------------------------------------------------


async def _fetch_stac_items(
    stac_cfg: dict[str, Any],
) -> list[tuple[str, str]]:
    """Search a STAC catalog and return (item_id, item_url) pairs.

    Parameters:
        stac_cfg: The ``stac_search`` block from the pipeline source.

    Returns:
        List of ``(item_id, item_url)`` tuples.

    Raises:
        PipelineError: If the search fails or returns no items.
    """
    try:
        from earthforge.core.config import EarthForgeProfile
        from earthforge.stac.search import search_catalog
    except ImportError as exc:
        raise PipelineError(f"earthforge-stac not installed: {exc}") from exc

    api = stac_cfg["api"]
    collection = stac_cfg["collection"]
    bbox: list[float] | None = stac_cfg.get("bbox")
    datetime_range: str | None = stac_cfg.get("datetime")
    limit: int = int(stac_cfg.get("limit", 10))

    profile = EarthForgeProfile(name="pipeline", stac_api=api, storage_backend="local")

    logger.info("Searching %s / %s (limit=%d)…", api, collection, limit)
    results = await search_catalog(
        profile,
        collections=[collection],
        bbox=bbox,
        datetime_range=datetime_range,
        max_items=limit,
    )

    if not results.items:
        raise PipelineError(
            f"STAC search returned no items for collection '{collection}'"
        )

    # Build item URL from self link
    pairs: list[tuple[str, str]] = []
    for item in results.items:
        self_link = item.links.get("self") if hasattr(item, "links") else None
        item_url = self_link or item.href if hasattr(item, "href") else ""
        if not item_url:
            # Construct URL from API root + items path
            item_url = f"{api.rstrip('/')}/collections/{collection}/items/{item.id}"
        pairs.append((item.id, item_url))

    logger.info("Found %d items", len(pairs))
    return pairs


# ---------------------------------------------------------------------------
# Per-item step execution
# ---------------------------------------------------------------------------


async def _run_for_each_item(
    step_list: list[dict[str, Any]],
    item_id: str,
    item_url: str,
    output_dir: Path,
    profile: str,
) -> ItemResult:
    """Execute a ``for_each_item`` step list for a single STAC item.

    Parameters:
        step_list: List of step dicts from the ``for_each_item`` block.
        item_id: STAC item ID.
        item_url: URL of the STAC item JSON.
        output_dir: Root output directory; item gets ``output_dir/item_id``.
        profile: EarthForge profile name.

    Returns:
        :class:`ItemResult` describing success/failure for this item.
    """
    t0 = time.perf_counter()
    item_dir = output_dir / item_id
    item_dir.mkdir(parents=True, exist_ok=True)

    ctx = StepContext(
        item_id=item_id,
        item_url=item_url,
        output_dir=item_dir,
        profile=profile,
    )

    step_results: list[dict[str, Any]] = []

    for step_dict in step_list:
        if len(step_dict) != 1:
            raise StepError("(unknown)", item_id, f"Step must have exactly one key: {step_dict}")

        step_name, step_params = next(iter(step_dict.items()))
        ctx.params = step_params or {}

        logger.debug("Item %s: running step %s", item_id, step_name)
        try:
            fn = get_step(step_name)
        except KeyError as exc:
            return ItemResult(
                item_id=item_id,
                item_url=item_url,
                succeeded=False,
                steps=step_results,
                error=str(exc),
                elapsed_seconds=time.perf_counter() - t0,
            )

        try:
            result: StepResult = await fn(ctx)
            step_results.append(
                {
                    "step": step_name,
                    "outputs": result.outputs,
                    "elapsed_seconds": round(result.elapsed_seconds, 3),
                    "message": result.message,
                }
            )
            # Merge new outputs into asset_paths for the next step
            ctx.asset_paths.update(result.outputs)

        except StepError as exc:
            logger.warning("Step %s failed for item %s: %s", step_name, item_id, exc)
            return ItemResult(
                item_id=item_id,
                item_url=item_url,
                succeeded=False,
                steps=step_results,
                error=str(exc),
                elapsed_seconds=time.perf_counter() - t0,
            )

    return ItemResult(
        item_id=item_id,
        item_url=item_url,
        succeeded=True,
        steps=step_results,
        elapsed_seconds=round(time.perf_counter() - t0, 3),
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_pipeline(
    doc: dict[str, Any],
    *,
    output_dir: str | None = None,
    profile: str = "default",
    dry_run: bool = False,
) -> PipelineRunResult:
    """Execute a validated pipeline document.

    Fetches source STAC items, then runs the step graph concurrently across
    items using ``asyncio.TaskGroup`` bounded by the ``parallel`` setting.

    Parameters:
        doc: Parsed and validated pipeline document (from :func:`load_pipeline`).
        output_dir: Override the pipeline's ``output_dir`` setting.
        profile: EarthForge profile name for STAC and storage access.
        dry_run: If True, validate and plan the pipeline without executing steps.

    Returns:
        :class:`PipelineRunResult` with per-item results and summary statistics.

    Raises:
        PipelineValidationError: If the document fails schema validation.
        PipelineError: If the source fetch fails or no items are found.
    """
    t0 = time.perf_counter()

    validate_pipeline_doc(doc)
    pipeline_cfg = doc["pipeline"]

    name: str = pipeline_cfg["name"]
    parallel: int = int(pipeline_cfg.get("parallel", 4))
    out_dir = Path(output_dir or pipeline_cfg.get("output_dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fetch source items
    source_cfg = pipeline_cfg["source"]
    if "stac_search" in source_cfg:
        items = await _fetch_stac_items(source_cfg["stac_search"])
    else:
        raise PipelineError(
            f"Unsupported source type. Expected 'stac_search', got: {list(source_cfg)}"
        )

    if dry_run:
        logger.info("Dry run — skipping step execution for %d items", len(items))
        return PipelineRunResult(
            pipeline_name=name,
            items_total=len(items),
            items_succeeded=0,
            items_failed=0,
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    # Build the per-item step list from for_each_item blocks
    for_each_steps: list[dict[str, Any]] = []
    for step in pipeline_cfg["steps"]:
        if "for_each_item" in step:
            for_each_steps.extend(step["for_each_item"])

    if not for_each_steps:
        raise PipelineError(
            "Pipeline has no 'for_each_item' steps. "
            "Add at least one for_each_item block under 'steps'."
        )

    # Execute per-item concurrently
    semaphore = asyncio.Semaphore(parallel)
    item_results: list[ItemResult] = []

    async def _bounded(item_id: str, item_url: str) -> ItemResult:
        async with semaphore:
            return await _run_for_each_item(
                for_each_steps, item_id, item_url, out_dir, profile
            )

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_bounded(iid, iurl)) for iid, iurl in items]

    for task in tasks:
        item_results.append(task.result())

    succeeded = sum(1 for r in item_results if r.succeeded)
    failed = sum(1 for r in item_results if not r.succeeded)

    return PipelineRunResult(
        pipeline_name=name,
        items_total=len(items),
        items_succeeded=succeeded,
        items_failed=failed,
        item_results=item_results,
        elapsed_seconds=round(time.perf_counter() - t0, 3),
    )
