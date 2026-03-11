# Architecture

This document describes EarthForge's system design. It exists at the repo root because architecture is a first-class artifact of the project, not an afterthought. Detailed module interfaces and implementation patterns live in [`ai-dev/architecture.md`](ai-dev/architecture.md).

## Design Principles

**Library-first, CLI-second.** All business logic lives in domain packages (`earthforge.stac`, `earthforge.raster`, `earthforge.vector`, `earthforge.cube`). The CLI is a thin dispatch layer that parses arguments, calls library functions, and formats output. Anything you can do from the CLI, you can do from Python.

**Async-first I/O.** Cloud-native geospatial work is I/O-bound — STAC API calls, COG range requests, cloud storage access. The primary API is async. Synchronous wrappers exist for convenience, not as the canonical path. See [DL-002](ai-dev/decisions/DL-002-async-first-io.md).

**Structured output as a contract.** Every CLI command supports `--output json|table|csv|quiet`. JSON output is not a best-effort serialization of whatever the command happens to produce — it conforms to a Pydantic model schema that is versioned and tested. This makes EarthForge pipeline-friendly by design.

**Format detection, not format flags.** `earthforge info s3://bucket/file` auto-detects whether the file is a COG, GeoParquet, Zarr store, or STAC catalog. The user shouldn't need to know the format to inspect it.

**Composability over completeness.** EarthForge does not include a web server, a database, a tile cache, or an ML framework. It produces structured output that feeds into other tools. The scope boundary is deliberate — see [what EarthForge is not](README.md#what-earthforge-is-not).

## Package Structure

```
earthforge (meta-package)
├── earthforge-core (always installed)
│   ├── config      — Profile management, config.toml parsing
│   ├── storage     — S3/GCS/Azure/local via obstore (DL-003)
│   ├── http        — Async HTTP client (httpx wrapper)
│   ├── output      — Structured rendering: json, table, csv, quiet
│   ├── formats     — Format detection chain
│   ├── errors      — Exception hierarchy
│   └── types       — Shared types: BBox, CRS, TimeRange
├── earthforge-cli (optional: pip install earthforge[cli])
│   └── Typer app   — Thin dispatch, no business logic
├── earthforge-stac (optional: pip install earthforge[stac])
│   ├── search      — pystac-client wrapper with async + profiles
│   ├── info        — Item/collection/catalog inspection
│   ├── validate    — STAC spec validation
│   └── fetch       — Parallel asset download with resume
├── earthforge-raster (optional: pip install earthforge[raster])
│   ├── info        — COG metadata via rasterio
│   ├── validate    — COG compliance checking
│   ├── convert     — GeoTIFF → COG with sensible defaults
│   ├── preview     — Quicklook PNG via HTTP range requests
│   └── calc        — Band math with safe expression parsing
├── earthforge-vector (optional: pip install earthforge[vector])
│   ├── info        — GeoParquet schema, CRS, feature count
│   ├── validate    — GeoParquet schema compliance
│   ├── convert     — Shapefile/GeoJSON → GeoParquet/FlatGeobuf
│   └── query       — Spatial/attribute filtering with predicate pushdown
├── earthforge-cube (optional: pip install earthforge[cube])
│   ├── info        — Zarr dimensions, variables, chunks
│   ├── validate    — Zarr structure compliance
│   ├── convert     — NetCDF ↔ Zarr, rechunk
│   └── slice       — Spatiotemporal extraction
└── earthforge-rs (optional, Rust acceleration)
    ├── format detection  — Magic byte sniffing
    ├── range reads       — Parallel HTTP range assembly
    └── parquet I/O       — geoarrow-rs acceleration
```

## Dependency Flow

Dependencies point one direction: domain packages → core. Core never imports from domain packages. The CLI imports from domain packages via guarded optional imports that produce helpful error messages when a package isn't installed.

```
cli ──→ stac ──→ core
   ──→ raster ──→ core
   ──→ vector ──→ core
   ──→ cube ──→ core
```

No package at the same level imports from another (stac does not import from raster). Cross-domain workflows are composed at the CLI or pipeline layer, not inside the library.

## Rust Extension

The Rust extension (`packages/rs/`) accelerates three specific bottlenecks where Python's overhead is measurable: format detection across many files, parallel HTTP range reads, and GeoParquet I/O for large datasets. Everything else stays in Python.

The Rust extension is always optional. Every Rust-accelerated function has a pure-Python fallback. `pip install earthforge` works without a Rust toolchain. See [DL-005](ai-dev/decisions/DL-005-rust-boundary.md).

## Decision Records

Architectural decisions are documented in [`ai-dev/decisions/`](ai-dev/decisions/), following the ADR (Architectural Decision Record) pattern. Each record captures the context that prompted the decision, the decision itself, alternatives that were evaluated and rejected, and the consequences.

| Record | Decision |
|---|---|
| [DL-001](ai-dev/decisions/DL-001-monorepo.md) | Monorepo with Hatch workspace packages |
| [DL-002](ai-dev/decisions/DL-002-async-first-io.md) | Async-first I/O via httpx |
| [DL-003](ai-dev/decisions/DL-003-storage-abstraction.md) | obstore over fsspec for cloud storage |
| [DL-005](ai-dev/decisions/DL-005-rust-boundary.md) | Rust for format detection and range reads only |

New decisions are added as the project evolves. If you're contributing and encounter an architectural ambiguity, open an issue or propose a new decision record.
