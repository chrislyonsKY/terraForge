"""Tests for earthforge.pipeline.schema — YAML validation."""

from __future__ import annotations

import pytest

from earthforge.pipeline.errors import PipelineValidationError
from earthforge.pipeline.schema import validate_pipeline_doc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_doc(**overrides) -> dict:
    doc = {
        "pipeline": {
            "name": "test-pipeline",
            "source": {
                "stac_search": {
                    "api": "https://earth-search.aws.element84.com/v1",
                    "collection": "sentinel-2-l2a",
                }
            },
            "steps": [
                {"for_each_item": [{"stac.fetch": {"assets": ["B04"]}}]}
            ],
        }
    }
    doc["pipeline"].update(overrides)
    return doc


# ---------------------------------------------------------------------------
# Valid documents
# ---------------------------------------------------------------------------


class TestValidDocuments:
    def test_minimal_valid(self) -> None:
        validate_pipeline_doc(_base_doc())  # should not raise

    def test_with_bbox(self) -> None:
        doc = _base_doc()
        doc["pipeline"]["source"]["stac_search"]["bbox"] = [-85.5, 37.0, -84.0, 38.5]
        validate_pipeline_doc(doc)

    def test_with_datetime(self) -> None:
        doc = _base_doc()
        doc["pipeline"]["source"]["stac_search"]["datetime"] = "2025-06-01/2025-09-30"
        validate_pipeline_doc(doc)

    def test_with_parallel(self) -> None:
        validate_pipeline_doc(_base_doc(parallel=8))

    def test_with_output_dir(self) -> None:
        validate_pipeline_doc(_base_doc(output_dir="./output"))

    def test_with_query(self) -> None:
        doc = _base_doc()
        doc["pipeline"]["source"]["stac_search"]["query"] = {"eo:cloud_cover": {"lt": 20}}
        validate_pipeline_doc(doc)

    def test_multiple_steps(self) -> None:
        doc = _base_doc()
        doc["pipeline"]["steps"] = [
            {
                "for_each_item": [
                    {"stac.fetch": {"assets": ["B04", "B08"]}},
                    {"raster.calc": {
                        "expression": "(B08 - B04) / (B08 + B04)",
                        "output": "ndvi_{item_id}.tif",
                    }},
                    {"raster.convert": {"format": "COG"}},
                ]
            }
        ]
        validate_pipeline_doc(doc)


# ---------------------------------------------------------------------------
# Invalid documents
# ---------------------------------------------------------------------------


class TestInvalidDocuments:
    def test_missing_pipeline_key(self) -> None:
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc({"not_pipeline": {}})

    def test_missing_name(self) -> None:
        doc = _base_doc()
        del doc["pipeline"]["name"]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_missing_source(self) -> None:
        doc = _base_doc()
        del doc["pipeline"]["source"]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_missing_steps(self) -> None:
        doc = _base_doc()
        del doc["pipeline"]["steps"]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_empty_steps(self) -> None:
        doc = _base_doc(steps=[])
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_stac_search_missing_api(self) -> None:
        doc = _base_doc()
        del doc["pipeline"]["source"]["stac_search"]["api"]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_stac_search_missing_collection(self) -> None:
        doc = _base_doc()
        del doc["pipeline"]["source"]["stac_search"]["collection"]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_bbox_wrong_length(self) -> None:
        doc = _base_doc()
        doc["pipeline"]["source"]["stac_search"]["bbox"] = [-85.0, 37.0]
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_parallel_too_high(self) -> None:
        doc = _base_doc(parallel=100)
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)

    def test_extra_top_level_key(self) -> None:
        doc = _base_doc()
        doc["unexpected_key"] = "value"
        with pytest.raises(PipelineValidationError):
            validate_pipeline_doc(doc)
