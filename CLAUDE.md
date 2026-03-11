# CLAUDE.md — EarthForge

> Cloud-Native Geospatial Developer Toolkit
> Python 3.11+ · Hatch · Typer · PyO3/maturin · httpx · obstore

Read this file completely before doing anything.
Then read `ai-dev/architecture.md` for full system design.
Then read `ai-dev/guardrails/` for hard constraints that override all other guidance.

---

## Workflow Protocol

### Teach-As-You-Build

This project uses a **teach-as-you-build** workflow. After completing each component (file, module, function, configuration block), stop and explain:

1. **What you just wrote** — one sentence naming the component
2. **Why it exists** — what problem it solves or what role it fills in the architecture
3. **Why you made the specific choices you made** — library selections, patterns used, tradeoffs accepted
4. **How it connects** — what depends on this component, what this component depends on
5. **What to watch for** — common mistakes, things that could break, edge cases

Format explanations as a brief narrative paragraph, not bullet lists. Write as if teaching a senior developer who knows GIS and Python well but is encountering this specific architecture for the first time. Do not oversimplify — explain the *engineering reasoning*, not the syntax.

After the explanation, ask: **"Ready for the next component, or questions on this one?"**

Do not batch multiple components and explain them all at the end. Explain each one immediately after writing it. The goal is that the developer understands every line of this codebase as it's being built, not after.

### Task Execution

When starting a new task:
1. Read CLAUDE.md (this file)
2. Read `ai-dev/architecture.md`
3. Read `ai-dev/guardrails/` — these constraints override all other guidance
4. Read the relevant `ai-dev/agents/` file for your role
5. Check `ai-dev/decisions/` for prior decisions that may affect your work
6. Check `ai-dev/skills/` for domain patterns specific to this project

When implementing a feature:
1. State your understanding of the task
2. Identify which packages are affected
3. Show the plan (files to create/modify, interfaces to implement)
4. Do not write code until the user types **Engage**
5. After writing each component, follow the teach-as-you-build protocol above
6. After completing all components for the feature, summarize the full change set
7. **Validate against real-world data** — run the feature against the datasets in `ai-dev/test-data-plan.md`, record results in `ai-dev/validation-reports/`, commit the report alongside the code

A feature is not complete until:
- Unit tests pass with mocked I/O
- The feature has been run against real-world data from `ai-dev/test-data-plan.md`
- A validation report exists in `ai-dev/validation-reports/` documenting the actual results
- Any third-party validation tools have been run on output files (e.g., `rio cogeo validate` for COGs)

### Code Standards

When writing code:
- Every function gets a docstring (purpose, parameters, returns, raises)
- Every module gets a module-level docstring
- All I/O operations are async-first (sync wrappers are convenience layers)
- All HTTP calls go through `earthforge.core.http` (never raw httpx)
- All cloud storage calls go through `earthforge.core.storage` (never raw obstore/boto3)
- All CLI output goes through `earthforge.core.output` (never raw print/rich)
- Error handling in every function — no happy-path-only code

### Git Discipline

EarthForge's git history must reflect incremental, deliberate construction — not scaffold dumps.

**Commit messages** use Conventional Commits with package scope:
```
feat(core): add format detection chain with magic byte sniffing
fix(stac): handle pagination for STAC APIs without next link
test(raster): add COG validation tests for untiled GeoTIFF
```

**Commit granularity**: one logical change per commit. "Add format detection" is one commit. "Add format detection and fix a typo" is two commits.

**Do not create empty files.** No empty `__init__.py` files for packages that don't exist yet. No empty `tests/` directories. No skeleton files with only TODO markers. If a file is in the repo, it has working content and a reason to exist.

**Do not create directories for future work.** `packages/cube/` appears when cube functionality is implemented, not before. The project structure in this CLAUDE.md shows the *target* — the repo only contains what's been built.

**Every new module must ship with tests.** A module without tests is not complete. Write the test alongside the implementation, not as a separate follow-up task.

**AI-generated code must be reviewed and understood.** Do not commit code you cannot explain. If you used AI assistance, the result must still pass the "can you walk through this line by line" test.

---

## Compatibility Matrix

| Component | Version | Notes |
|---|---|---|
| Python | >=3.11 | Required for `tomllib`, `TaskGroup`, `StrEnum` |
| Hatch | >=1.7 | Workspace support |
| Typer | >=0.9 | CLI framework |
| httpx | >=0.27 | Async HTTP client |
| obstore | >=0.3 | S3/GCS/Azure storage abstraction |
| rasterio | >=1.3 | COG I/O |
| geopandas | >=0.14 | GeoParquet I/O |
| pystac-client | >=0.8 | STAC API client |
| xarray | >=2024.1 | Zarr/NetCDF datacube operations |
| maturin | >=1.0 | Rust extension build (packages/rs only) |
| Rust | >=1.70 | Rust extensions via PyO3 |
| ruff | >=0.4 | Linting and formatting |
| mypy | >=1.10 | Type checking (strict mode) |
| pytest | >=8.0 | Testing |

---

## Project Structure

```
earthforge/
├── CLAUDE.md                    ← You are here
├── README.md                    ← Human-facing: problem statement, install, usage examples
├── ARCHITECTURE.md              ← Human-facing: system design, dependency graph, decisions
├── CONTRIBUTING.md              ← Engineering standards, git conventions, scope boundaries
├── LICENSE                      ← Apache 2.0
├── pyproject.toml               ← Root workspace: Hatch config, optional deps, CLI entry point
├── ai-dev/                      ← AI development infrastructure (docs, agents, decisions)
├── packages/
│   ├── core/                    ← Shared types, config, storage, output formatting, format detection
│   ├── cli/                     ← Typer CLI — thin dispatch layer, no business logic
│   ├── stac/                    ← STAC catalog interaction (search, info, validate, fetch)
│   ├── raster/                  ← COG operations (info, validate, convert, preview, band math)
│   ├── vector/                  ← GeoParquet/FlatGeobuf operations (info, validate, convert, query)
│   ├── cube/                    ← Zarr/NetCDF datacube operations (info, validate, convert, slice)
│   └── rs/                      ← Rust acceleration extensions (PyO3/maturin)
├── plugins/
│   ├── qgis/                    ← QGIS plugin (deferred, separate build toolchain)
│   └── arcgis/                  ← ArcGIS Pro add-in (deferred, separate build toolchain)
├── examples/                    ← Runnable examples and pipeline YAML templates
├── benchmarks/                  ← Performance comparison scripts
└── docs/                        ← mkdocs-material documentation site
```

**Note:** The structure above is the *target*. The repo only contains directories for implemented functionality. `packages/cube/` does not exist until cube features are built and tested.

Each package under `packages/` uses the `src/earthforge/{domain}/` layout, enabling:
```python
from earthforge.core.config import load_profile
from earthforge.stac.search import search_catalog
from earthforge.raster.info import inspect_cog
```

The CLI package (`packages/cli/`) imports from domain packages and dispatches commands.
It contains NO business logic — only argument parsing and output formatting.

---

## Architecture Summary

EarthForge is a library-first, CLI-first toolkit. The library layer (`packages/core`, `packages/stac`, etc.) contains all business logic and exposes async Python APIs. The CLI layer (`packages/cli`) is a thin Typer application that calls library functions and formats output.

**I/O is async-first.** Every network operation uses async clients. The CLI wraps async calls with `asyncio.run()`. The library exposes async functions (primary) and sync wrappers (convenience).

**Storage is abstracted.** All cloud storage access goes through `earthforge.core.storage`, which wraps `obstore` for a unified `ObjectStore` interface across S3, GCS, Azure Blob, and local filesystem.

**Output is structured.** All CLI commands support `--output json|table|csv|quiet`. Commands return Python objects; the output module handles rendering.

**Format detection is centralized.** `earthforge.core.formats.detect()` uses a magic-bytes → extension → content-inspection chain to identify file formats.

See `ai-dev/architecture.md` for the complete system design.

---

## Critical Conventions

- **Import paths**: Always `from earthforge.{domain}.{module} import {name}`. Never relative imports across packages.
- **Async naming**: Async functions have no prefix. Sync wrappers get `_sync` suffix: `search()` is async, `search_sync()` is the wrapper.
- **Error types**: All exceptions inherit from `earthforge.core.errors.EarthForgeError`. Domain packages define subclasses.
- **CLI returns**: Commands return structured data (dataclasses/Pydantic models). The output formatter renders. Commands never call `print()`.
- **Configuration**: All configurable values flow through `earthforge.core.config`. No function accepts raw URLs or credentials.
- **Testing**: `respx` for async HTTP mocking. `pytest-recording` for VCR fixtures. Never make real network calls in unit tests.
- **Namespace packages**: No `__init__.py` at the `earthforge/` level. Only at `earthforge/core/`, `earthforge/stac/`, etc. This enables implicit namespace package merging across pip installs.
- **Rust fallback**: Always guard Rust extension imports with try/except and fall back to pure Python.

---

## What NOT To Do

- Do NOT use `fsspec` for storage abstraction. Use `obstore` via `earthforge.core.storage`. See DL-003.
- Do NOT use `requests` or `urllib3` for HTTP. Use `httpx` via `earthforge.core.http`.
- Do NOT put business logic in the CLI layer. CLI commands are thin wrappers.
- Do NOT use `print()` or `rich.print()` directly in library code. Use `earthforge.core.output`.
- Do NOT use `hatchling` as the build backend for `packages/rs/`. Use `maturin`. See DL-005.
- Do NOT create synchronous-first APIs with async bolted on. Async is the primary API.
- Do NOT hardcode STAC API URLs or cloud credentials. Use profiles via `earthforge.core.config`.
- Do NOT add an "ai" or "services" package without a bounded scope documented in a decision record.
- Do NOT create separate CI workflows per package. One workflow, one matrix.
- Do NOT use `eval()` or `exec()` for band math expressions in the pipeline runner.
- Do NOT put a `earthforge/__init__.py` at the namespace level. Namespace packages require its absence.
- Do NOT create empty directories or skeleton files for future work. If it's in the repo, it works.
- Do NOT commit a single "initial commit" with the entire project. Build incrementally — architecture first, then core, then features with tests.
- Do NOT commit AI-generated code without reading and understanding every line.
- Do NOT add Kubernetes manifests, Helm charts, Docker Compose files, or orchestration infrastructure. EarthForge is a CLI toolkit, not a platform.
