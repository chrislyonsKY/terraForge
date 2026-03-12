# VR-M3-pipeline-run — Pipeline Runner Validation

**Date:** 2026-03-12
**Module:** `earthforge.pipeline`
**Stage:** Milestone 3c

---

## Unit Test Results

```
packages/pipeline/tests/test_pipeline_schema.py    16 passed
packages/pipeline/tests/test_pipeline_steps.py     18 passed
packages/pipeline/tests/test_pipeline_runner.py    15 passed
Total: 49 passed in 4.21s
```

---

## Component Validation

### Schema Validation

Validated `validate_pipeline_doc` against the JSON Schema (Draft 2020-12):

| Test | Result |
|---|---|
| Minimal valid document | PASS |
| Document with bbox, datetime, query, parallel | PASS |
| Multi-step for_each_item block | PASS |
| Missing `name` field | Correctly rejected |
| Missing `source` field | Correctly rejected |
| Empty `steps` array | Correctly rejected |
| `bbox` with 2 elements instead of 4 | Correctly rejected |
| `parallel` > 32 | Correctly rejected |
| Extra top-level key | Correctly rejected |

### Safe Expression Evaluator

NDVI expression `(B08 - B04) / (B08 + B04)` evaluated with numpy float32 arrays:

| Input | B04 | B08 | Expected NDVI | Computed |
|---|---|---|---|---|
| Pixel 0 | 0.1 | 0.6 | 0.714 | 0.714 (PASS) |
| Pixel 1 | 0.2 | 0.8 | 0.600 | 0.600 (PASS) |

Rejected expressions (no eval/exec used — AST walker only):

| Expression | Rejection Reason |
|---|---|
| `abs(x)` | Function call — unsupported node |
| `x.shape` | Attribute access — unsupported node |
| `"hello"` | String constant — unsupported type |
| `(a + b` | SyntaxError in `ast.parse` |
| `x + y` with only `x` in env | Unknown variable |

### Step Registry

4 built-in steps registered at module import:

| Step | Description |
|---|---|
| `stac.fetch` | Download STAC item assets |
| `raster.calc` | Evaluate band math expression |
| `raster.convert` | Convert raster to COG |
| `vector.convert` | Convert vector to GeoParquet |

### Pipeline Execution (Mocked Source)

3 items, `parallel=2`, noop step:

| Metric | Value |
|---|---|
| Items total | 3 |
| Items succeeded | 3 |
| Items failed | 0 |
| Elapsed | 0.006s |

Concurrent execution confirmed: semaphore bounds at `parallel=2`, `asyncio.TaskGroup`
dispatches all items concurrently within that bound.

---

## NDVI Pipeline YAML (examples/scripts/ndvi_pipeline.yaml)

Validates cleanly against the JSON Schema:

```
earthforge pipeline validate examples/scripts/ndvi_pipeline.yaml → VALID
```

The pipeline targets Lexington, KY (`bbox: [-84.6, 37.9, -84.4, 38.1]`),
searches Sentinel-2 L2A for <20% cloud cover scenes in summer 2025,
downloads B04 + B08, computes NDVI, converts to COG.

---

## Notes on Full End-to-End Run

Full execution (real Sentinel-2 bands, not synthetic) requires:
- Internet access to Element84 Earth Search
- `rasterio` with GDAL installed in the test environment
- ~100–600 MB per band download per item

The `raster.calc` and `raster.convert` integration tests (`test_computes_result`)
pass in the ArcGIS Pro Python environment which has rasterio available. The
COG output from `raster.convert` should be validated with `rio cogeo validate`
after a real run; this is recorded as a follow-up once CI has network access.

---

## Template Validation

`earthforge pipeline init` outputs the NDVI template, which is valid YAML
and passes schema validation without modification.
