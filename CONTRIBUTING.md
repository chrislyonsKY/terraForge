# Contributing to TerraForge

TerraForge is an open-source project with specific engineering standards. This document describes what we expect from contributions and why. Please read it before opening a PR.

## Prerequisites

- Python 3.11+
- [Hatch](https://hatch.pypa.io/) for build and environment management
- [ruff](https://docs.astral.sh/ruff/) for linting
- [mypy](https://mypy.readthedocs.io/) for type checking
- Rust toolchain (optional, only for `packages/rs/` work)

## Setup

```bash
git clone https://github.com/chrislyonsKY/terraforge.git
cd terraforge
pip install -e ".[all,dev]"
```

## Engineering Standards

These aren't suggestions — they're the quality gate for merging. PRs that don't meet these standards will be sent back for revision.

### Every function gets a type annotation

mypy runs in strict mode. Every function parameter has a type, every return value has a type. No `Any` unless there's a documented reason. This catches real bugs — a function returning `dict` instead of `RasterInfoResult` breaks the JSON output contract silently without type checking.

### Every function gets error handling

No happy-path-only code. If a function opens a file, it handles the file-not-found case. If it makes an HTTP request, it handles timeouts and connection errors. If it parses user input, it validates before processing. Exceptions are specific (`CogValidationError`, not `Exception`) and include actionable messages ("Missing overviews. Convert with: `terraforge raster convert {path} --to cog`").

### Every I/O function is async

The primary API is async. If your function makes a network call or reads from cloud storage, it must be `async def`. Provide a `_sync` suffixed wrapper that calls `asyncio.run()`. The async version is the canonical implementation — the sync wrapper is convenience. See [DL-002](ai-dev/decisions/DL-002-async-first-io.md).

### No business logic in the CLI layer

CLI command handlers parse arguments, call a library function, and format the output. That's it. If your CLI handler is longer than 15 lines or imports anything other than `terraforge.*`, `typer`, and `asyncio`, logic has leaked into the wrong layer.

### No direct third-party imports in domain code

Domain packages (`stac`, `raster`, `vector`, `cube`) access HTTP via `terraforge.core.http`, storage via `terraforge.core.storage`, and output via `terraforge.core.output`. Never import `httpx`, `obstore`, or `rich` directly in domain code. This keeps the abstraction boundaries clean and makes it possible to swap implementations without touching every module.

### Return types are structured, not dicts

Functions return frozen dataclasses or Pydantic models. Not `dict[str, Any]`. Structured return types enable type-safe JSON serialization, IDE autocompletion, and schema generation. If you need a new return type, define it in the module where it's used.

### Tests mock all I/O

Unit tests use `respx` for async HTTP mocking and obstore's local filesystem backend for storage. Never make real network calls in unit tests. Tests tagged `@pytest.mark.integration` can hit real APIs — these are excluded from CI and run periodically.

## Running Quality Checks

```bash
# All three must pass before opening a PR
ruff check packages/
mypy
pytest
```

## Real-World Validation

TerraForge features must work against real data, not just mocked test fixtures. After implementing any feature that processes geospatial data:

1. Run it against the datasets listed in `ai-dev/test-data-plan.md` — these are real COGs on S3, real STAC APIs, real GeoParquet from Overture Maps, real Zarr climate stores
2. Record the results in `ai-dev/validation-reports/VR-{milestone}-{feature}.md` using the template in that directory
3. For format conversions, validate outputs with third-party tools (`rio cogeo validate` for COGs, `gpq validate` for GeoParquet)
4. Commit the validation report alongside the code

A PR that adds a new command without a validation report will be sent back. Mocked tests prove the logic works. Real-world tests prove the tool works. We need both.

ruff enforces `T20` (no print statements in library code), `DTZ` (no naive datetimes), `S307` (no eval/exec), and `B` (common Python gotchas). If ruff flags something, don't add a `noqa` comment unless you can explain why the rule doesn't apply.

## Git Conventions

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with the package as scope:

```
feat(core): add format detection chain with magic byte sniffing
fix(stac): handle pagination for STAC APIs without next link
docs(decisions): add DL-006 output format contract
test(raster): add COG validation tests for untiled GeoTIFF
refactor(cli): extract global flags into shared callback
chore(ci): add mypy strict mode to CI pipeline
```

The scope tells reviewers which package is affected without opening the diff. The verb tells them the nature of the change. This isn't cosmetic — it's how the changelog gets generated and how the git history stays navigable.

### Commit Granularity

Each commit should represent one logical change. "Add format detection" is one commit. "Add format detection, fix a typo in the README, and update the CI config" is three commits. Squash cleanup before merge if needed, but keep the logical separation.

### Branch Naming

```
feat/core-format-detection
fix/stac-pagination-edge-case
docs/contributing-guide
```

### What Not to Commit

- Scaffold dumps with dozens of empty files and TODO markers. If a file doesn't have working code and at least one test, it doesn't belong in the repo.
- Generated code without review. AI-assisted code is welcome — but it must be reviewed, tested, and understood by the contributor. If you can't explain what a function does and why, don't commit it.
- "Initial commit" blobs with the entire project. Build incrementally. Architecture docs first, then core interfaces, then features with tests. The git history should tell the story of how the project was built.

## Architecture Decisions

If your contribution involves a new dependency, a new package, a new storage backend, or any change to the module interfaces in `ARCHITECTURE.md`, it needs a decision record in `ai-dev/decisions/`. Use the existing records as a template. The key sections are Context (why the decision is needed), Decision (what was decided), Alternatives Considered (what else was evaluated and why it was rejected), and Consequences (what this enables and constrains).

Decision records exist so that future contributors — including AI coding tools — don't re-argue settled decisions. If you think a previous decision should be revisited, open an issue referencing the decision record and explaining what has changed.

## Scope Boundaries

TerraForge is a composable CLI toolkit for cloud-native geospatial data. Contributions that expand the scope beyond this need explicit discussion before implementation:

- No web servers or API endpoints (use TiTiler, stac-fastapi)
- No databases or persistent state (use PostGIS)
- No ML/AI modules without a bounded, specific scope documented in a decision record
- No Kubernetes manifests, Helm charts, or orchestration infrastructure
- No GUI components (the TUI explorer is terminal-based and opt-in)

These boundaries are deliberate, not gaps waiting to be filled. If you think the scope should expand, make the case in an issue — don't submit a PR that assumes the answer is yes.

## Questions

Open an issue or start a discussion. We'd rather answer questions before you write code than review a PR that went in the wrong direction.
