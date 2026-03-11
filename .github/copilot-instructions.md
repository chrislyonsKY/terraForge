# Copilot Instructions — EarthForge

> Cloud-Native Geospatial Developer Toolkit
> Python 3.11+ · Hatch · Typer · PyO3/maturin · httpx · obstore

## Teach-As-You-Build Protocol

After completing each component (file, module, function, config block), immediately explain:
1. What you just wrote (one sentence)
2. Why it exists and why you made the specific choices you made
3. How it connects to the rest of the system
4. What to watch for (common mistakes, edge cases)

Write explanations as narrative for a senior developer who knows GIS and Python but is encountering this architecture for the first time. Do not oversimplify. After explaining, ask: "Ready for the next component, or questions on this one?"

Do not batch explanations. Explain each component immediately after writing it.

## Architecture

- **Monorepo** with Hatch workspace packages under `packages/`
- **Library-first, CLI-second**: Business logic in domain packages, CLI is thin dispatch
- **Async-first I/O**: httpx for HTTP, obstore for cloud storage, asyncio.run() at CLI entry
- **Namespace packages**: No `earthforge/__init__.py` — packages merge via PEP 420
- **Structured output**: Commands return Pydantic models, output module renders json/table/csv

## Packages

| Package | Role | Key Dependencies |
|---|---|---|
| `core` | Config, storage, output, format detection, error types | httpx, obstore, pydantic, rich |
| `cli` | Typer CLI, argument parsing, output formatting | typer, core |
| `stac` | STAC search, info, validate, fetch | pystac-client, core |
| `raster` | COG info, validate, convert, preview, band math | rasterio, numpy, Pillow, core |
| `vector` | GeoParquet info, validate, convert, query | geopandas, pyarrow, core |
| `cube` | Zarr/NetCDF info, validate, convert, slice | xarray, zarr, core |
| `rs` | Rust acceleration (format detection, range reads) | PyO3, maturin (NOT hatchling) |

## Hard Rules

- All I/O through `earthforge.core.http` or `earthforge.core.storage` — never raw httpx/obstore
- All output through `earthforge.core.output` — never `print()`
- All exceptions inherit `earthforge.core.errors.EarthForgeError`
- No business logic in CLI layer
- No `eval()`/`exec()` for expressions
- No hardcoded URLs or credentials — use `earthforge.core.config` profiles
- Rust extension: always provide pure-Python fallback via try/except import
- `packages/rs/` uses maturin build backend, not hatchling
- No empty files, skeleton directories, or TODO-only stubs — if it's in the repo, it works
- No single "initial commit" dumps — build incrementally, one logical change per commit
- No AI-generated code committed without the contributor understanding every line

## Git Conventions

Conventional Commits with package scope:
```
feat(core): add format detection chain with magic byte sniffing
fix(stac): handle pagination for STAC APIs without next link
test(raster): add COG validation tests for untiled GeoTIFF
```

Every new module ships with tests. A module without tests is not complete.

## Real-World Validation

Every feature must be tested against the real-world datasets in `ai-dev/test-data-plan.md` before it ships. Record results in `ai-dev/validation-reports/VR-{milestone}-{feature}.md`. A feature without a validation report is not complete.

## Read First

- `CLAUDE.md` — full project context
- `ai-dev/architecture.md` — system design
- `ai-dev/guardrails/` — constraints that override all other guidance
- `ai-dev/decisions/` — settled architectural decisions
