# DL-001: Monorepo Over Multi-Repo

**Date:** 2026-03-10
**Status:** Accepted
**Author:** Chris Lyons

## Context

The initial TerraForge scaffold created 15 separate package directories, each with independent pyproject.toml, CI workflow, Dockerfile, README, and copilot-instructions.md. An audit revealed all 15 packages were byte-identical templates — same CI, same copilot-instructions (identical md5 hashes), same empty `src/` directories, no source code, no tests, no differentiation.

The question: should TerraForge launch as 15 independent repositories or as a single monorepo with workspace packages?

## Decision

TerraForge uses a monorepo with Hatch workspace packages under a `packages/` directory. Each package retains its own `pyproject.toml` for independent installability, but shares a single git repository, CI pipeline, and version policy.

QGIS and ArcGIS plugins live in `plugins/` (not `packages/`) because they have genuinely different build toolchains and release cadences.

## Alternatives Considered

- **15 independent repos (original design)** — Rejected. Zero code exists to differentiate packages, so the overhead of 15 CI pipelines, 15 separate PRs for cross-cutting changes, and cross-repo version pinning provides no benefit. Contributor friction is the highest risk to an early-stage open-source project.
- **Single package (no workspace)** — Rejected. `pip install terraforge[stac]` selectivity requires separate package declarations. A single flat package forces users to install all dependencies.

## Consequences

- Single CI matrix, single contributor workflow, single PR for cross-cutting features
- Packages can be extracted to independent repos later when genuine independent release cycles are needed
- Hatch workspace support requires Hatch >=1.7
- Namespace package pattern (no `terraforge/__init__.py`) requires all packages to follow the same convention — a single mistake breaks imports

## References

- Scaffold audit: all 15 copilot-instructions.md had identical md5 `74e305d0804fcb2181c0256da477a4d1`
- Hatch workspace docs: https://hatch.pypa.io/latest/config/build/
