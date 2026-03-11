# Coding Standards Guardrails

These rules apply to ALL code generated for this project, regardless of which agent is active. Violations are treated as Critical findings. When a guardrail conflicts with any other instruction, the guardrail wins.

## Python

- Target Python 3.11+ — use `tomllib`, `StrEnum`, `TaskGroup`, `type X = Y` syntax freely
- All source formatted and linted by ruff — do not override ruff rules inline without justification in a code comment
- All public functions and classes must have type annotations — mypy strict mode is enforced
- All functions must include error handling — no happy-path-only code
- All I/O functions must be async-first — sync wrappers are convenience, not primary
- All database/network resources must use `async with` or `with` context managers — no manual open/close
- No `print()` statements in library code (packages other than cli) — enforced by ruff T20 rule
- No `eval()` or `exec()` anywhere — enforced by ruff S307 rule
- No bare `except:` clauses — always catch specific exceptions
- Logging via `structlog` or stdlib `logging` — never bare print for diagnostics
- Import style: `from earthforge.{domain}.{module} import {name}` — no relative cross-package imports

## Dependencies

- No package may import from another domain package at the same level (stac cannot import from raster)
- All domain packages depend on core; core depends on no domain package
- CLI imports domain packages via guarded try/except for optional dependency support
- Third-party libraries are accessed through core wrappers, not imported directly by domain code:
  - HTTP: `earthforge.core.http`, not `httpx` directly
  - Storage: `earthforge.core.storage`, not `obstore` directly
  - Output: `earthforge.core.output`, not `rich` directly

## Packaging

- Namespace packages: NO `__init__.py` at `earthforge/` level — only at `earthforge/{domain}/` level
- Each package's `pyproject.toml` declares only its direct dependencies
- `packages/rs/` uses maturin build backend — never hatchling
- Version pinning: use `>=X.Y` minimum pins, not `==X.Y.Z` exact pins (leave exact pinning to lockfiles)

## Testing

### Unit Tests
- No real network calls in unit tests — use respx for HTTP mocking, obstore local backend for storage
- Every public function must have at least one test
- Async test functions are auto-detected via `asyncio_mode = "auto"`
- Integration tests marked `@pytest.mark.integration` and excluded from default CI runs

### Real-World Validation (Non-Negotiable)

No feature is complete until it has been tested against real-world data and the results are documented. Mocked tests prove the logic works. Real-world tests prove the tool works.

After implementing any command or library function that processes geospatial data:

1. **Run it against the real-world test datasets** listed in `ai-dev/test-data-plan.md`
2. **Record the results** in `ai-dev/validation-reports/` — one report per feature, named `VR-{milestone}-{feature}.md`
3. **Include in the report**: exact command run, actual output (truncated if large), pass/fail against expected output, any unexpected behavior, performance observations (time to complete, data transferred)
4. **If a real-world test fails**, the feature is not complete — fix the code, re-run, update the report

Validation reports are committed to the repo alongside the code they validate. A PR that adds a new command without a validation report will be sent back.

This applies to:
- Format detection (`earthforge info`) — must correctly identify real COGs, GeoParquet, Zarr, and non-cloud-native files
- STAC search — must return results from real STAC APIs (Element84 Earth Search, Planetary Computer)
- Raster operations — must work against real COGs on S3, not just synthetic test files
- Vector operations — must handle real GeoParquet with real geometries, not toy 3-row fixtures
- Cube operations — must read real Zarr stores, not just in-memory test arrays
- Format conversion — output must pass validation by third-party tools (rio cogeo validate, STAC validator)
- Pipeline execution — must complete end-to-end against real remote data
