"""Tests for earthforge.pipeline.runner — pipeline execution engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from earthforge.pipeline.errors import PipelineError, PipelineValidationError
from earthforge.pipeline.runner import (
    PipelineRunResult,
    load_pipeline,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_doc(**overrides) -> dict:
    doc = {
        "pipeline": {
            "name": "test",
            "source": {
                "stac_search": {
                    "api": "https://earth-search.aws.element84.com/v1",
                    "collection": "sentinel-2-l2a",
                }
            },
            "steps": [{"for_each_item": [{"stac.fetch": {"assets": ["B04"]}}]}],
        }
    }
    doc["pipeline"].update(overrides)
    return doc


# ---------------------------------------------------------------------------
# load_pipeline
# ---------------------------------------------------------------------------


class TestLoadPipeline:
    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "pipe.yaml"
        p.write_text(
            "pipeline:\n"
            "  name: test\n"
            "  source:\n"
            "    stac_search:\n"
            "      api: https://example.com\n"
            "      collection: sentinel-2-l2a\n"
            "  steps:\n"
            "    - for_each_item:\n"
            "        - stac.fetch: {}\n"
        )
        doc = load_pipeline(str(p))
        assert doc["pipeline"]["name"] == "test"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PipelineError, match="Cannot read"):
            load_pipeline(str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("pipeline: [\nbad yaml")
        with pytest.raises(PipelineValidationError):
            load_pipeline(str(p))


# ---------------------------------------------------------------------------
# run_pipeline — dry_run mode (no network, no step execution)
# ---------------------------------------------------------------------------


class TestRunPipelineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_no_steps_executed(self, tmp_path: Path) -> None:
        doc = _base_doc()

        fake_items = [
            ("S2A_001", "https://example.com/S2A_001"),
            ("S2A_002", "https://example.com/S2A_002"),
        ]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path), dry_run=True)

        assert result.pipeline_name == "test"
        assert result.items_total == 2
        assert result.items_succeeded == 0
        assert result.items_failed == 0
        assert result.item_results == []

    @pytest.mark.asyncio
    async def test_dry_run_elapsed_recorded(self, tmp_path: Path) -> None:
        doc = _base_doc()
        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=[("A", "https://x.com/A")]),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path), dry_run=True)
        assert result.elapsed_seconds >= 0


# ---------------------------------------------------------------------------
# run_pipeline — step execution with mocked steps
# ---------------------------------------------------------------------------


class TestRunPipelineExecution:
    @pytest.mark.asyncio
    async def test_successful_run(self, tmp_path: Path) -> None:
        from earthforge.pipeline.steps import StepResult, register_step

        @register_step("test.noop_abc")
        async def noop(ctx):
            return StepResult(step_name="test.noop_abc", item_id=ctx.item_id, message="ok")

        doc = _base_doc(steps=[{"for_each_item": [{"test.noop_abc": {}}]}])
        fake_items = [("ITEM_A", "https://example.com/ITEM_A")]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path))

        assert result.items_total == 1
        assert result.items_succeeded == 1
        assert result.items_failed == 0
        assert result.item_results[0].succeeded is True

    @pytest.mark.asyncio
    async def test_step_failure_recorded_per_item(self, tmp_path: Path) -> None:
        from earthforge.pipeline.errors import StepError
        from earthforge.pipeline.steps import register_step

        @register_step("test.always_fail_xyz")
        async def fail_step(ctx):
            raise StepError("test.always_fail_xyz", ctx.item_id, "intentional failure")

        doc = _base_doc(steps=[{"for_each_item": [{"test.always_fail_xyz": {}}]}])
        fake_items = [("ITEM_FAIL", "https://example.com/ITEM_FAIL")]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path))

        assert result.items_failed == 1
        assert result.items_succeeded == 0
        assert result.item_results[0].succeeded is False
        assert "intentional failure" in result.item_results[0].error

    @pytest.mark.asyncio
    async def test_parallel_items(self, tmp_path: Path) -> None:
        from earthforge.pipeline.steps import StepResult, register_step

        @register_step("test.noop_parallel_xyz")
        async def noop(ctx):
            return StepResult(step_name="test.noop_parallel_xyz", item_id=ctx.item_id)

        doc = _base_doc(
            parallel=3,
            steps=[{"for_each_item": [{"test.noop_parallel_xyz": {}}]}],
        )
        fake_items = [(f"ITEM_{i}", f"https://x.com/{i}") for i in range(6)]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path))

        assert result.items_total == 6
        assert result.items_succeeded == 6

    @pytest.mark.asyncio
    async def test_unknown_step_fails_item(self, tmp_path: Path) -> None:
        doc = _base_doc(steps=[{"for_each_item": [{"step.that.does.not.exist": {}}]}])
        fake_items = [("ITEM_X", "https://x.com/X")]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            result = await run_pipeline(doc, output_dir=str(tmp_path))

        assert result.items_failed == 1

    @pytest.mark.asyncio
    async def test_no_for_each_steps_raises(self, tmp_path: Path) -> None:
        # A pipeline with steps but no for_each_item block
        doc = _base_doc(steps=[{"some_other_step": {}}])
        fake_items = [("X", "https://x.com/X")]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            with pytest.raises(PipelineError, match="no 'for_each_item' steps"):
                await run_pipeline(doc, output_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_output_dir_created(self, tmp_path: Path) -> None:
        from earthforge.pipeline.steps import StepResult, register_step

        @register_step("test.noop_dir_xyz")
        async def noop(ctx):
            return StepResult(step_name="test.noop_dir_xyz", item_id=ctx.item_id)

        out = tmp_path / "nested" / "output"
        doc = _base_doc(steps=[{"for_each_item": [{"test.noop_dir_xyz": {}}]}])
        fake_items = [("ITEM_Z", "https://x.com/Z")]

        with patch(
            "earthforge.pipeline.runner._fetch_stac_items",
            new=AsyncMock(return_value=fake_items),
        ):
            await run_pipeline(doc, output_dir=str(out))

        assert out.exists()


# ---------------------------------------------------------------------------
# PipelineRunResult model
# ---------------------------------------------------------------------------


class TestPipelineRunResultModel:
    def test_serializes_to_json(self) -> None:
        import json

        result = PipelineRunResult(
            pipeline_name="test",
            items_total=3,
            items_succeeded=2,
            items_failed=1,
            elapsed_seconds=4.5,
        )
        doc = json.loads(result.model_dump_json())
        assert doc["pipeline_name"] == "test"
        assert doc["items_succeeded"] == 2
