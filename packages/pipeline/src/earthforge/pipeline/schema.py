"""JSON Schema definition and validation for EarthForge pipeline documents.

The schema validates the top-level ``pipeline`` key and all nested structures.
Validation uses ``jsonschema`` for compatibility with the standard ecosystem
(unlike Pydantic, jsonschema can validate dict structures loaded from YAML
without a full model hierarchy).

The pipeline document structure::

    pipeline:
      name: <str>               # Human-readable name
      description: <str>        # Optional description
      output_dir: <str>         # Root output directory (default: ./output)
      parallel: <int>           # Max concurrent item workers (default: 4)
      source:
        stac_search:
          api: <str>            # STAC API URL
          collection: <str>     # Collection ID
          bbox: [W, S, E, N]    # Optional spatial filter
          datetime: <str>       # Optional datetime range
          query: <dict>         # Optional CQL2 filter
          limit: <int>          # Max items (default: 10)
      steps:
        - for_each_item:        # Per-item concurrent step list
            - <step_name>:
                <step_params>
        - <step_name>:          # Top-level (non-per-item) steps
            <step_params>
"""

from __future__ import annotations

from typing import Any

from earthforge.pipeline.errors import PipelineValidationError

# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

PIPELINE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "EarthForge Pipeline",
    "type": "object",
    "required": ["pipeline"],
    "additionalProperties": False,
    "properties": {
        "pipeline": {
            "type": "object",
            "required": ["name", "source", "steps"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "output_dir": {"type": "string", "default": "./output"},
                "parallel": {"type": "integer", "minimum": 1, "maximum": 32, "default": 4},
                "source": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 1,
                    "properties": {
                        "stac_search": {
                            "type": "object",
                            "required": ["api", "collection"],
                            "additionalProperties": False,
                            "properties": {
                                "api": {"type": "string", "format": "uri"},
                                "collection": {"type": "string"},
                                "bbox": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "minItems": 4,
                                    "maxItems": 4,
                                },
                                "datetime": {"type": "string"},
                                "query": {"type": "object"},
                                "limit": {"type": "integer", "minimum": 1, "default": 10},
                            },
                        }
                    },
                },
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "minProperties": 1,
                        "maxProperties": 1,
                    },
                },
            },
        }
    },
}


def validate_pipeline_doc(doc: dict[str, Any]) -> None:
    """Validate a parsed pipeline YAML document against the pipeline schema.

    Parameters:
        doc: Parsed YAML as a Python dict.

    Raises:
        PipelineValidationError: If the document does not conform to the schema.
    """
    try:
        import jsonschema
    except ImportError as exc:
        raise PipelineValidationError(
            "jsonschema is required for pipeline validation: pip install earthforge[pipeline]"
        ) from exc

    validator = jsonschema.Draft202012Validator(PIPELINE_SCHEMA)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))

    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise PipelineValidationError(first.message, path=path)
