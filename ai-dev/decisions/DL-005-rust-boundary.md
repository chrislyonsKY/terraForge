# DL-005: Rust Extension Boundary

**Date:** 2026-03-10
**Status:** Accepted
**Author:** Chris Lyons

## Context

TerraForge uses PyO3/maturin for Rust extensions. The boundary between Rust and Python determines build complexity, contributor accessibility, and fallback behavior when the Rust extension isn't available.

## Decision

Rust handles three specific performance-critical paths. Everything else stays in Python.

### In Rust (packages/rs)

1. **Format detection** — Magic byte sniffing across many files. Pure byte manipulation where per-byte Python object overhead is measurable.
2. **Parallel HTTP range reads** — Issuing 50+ concurrent range requests and assembling results into contiguous arrays. Tokio async runtime + zero-copy outperforms Python asyncio + memoryview.
3. **GeoParquet I/O via geoarrow-rs** — For files >1GB, Rust Arrow read → zero-copy transfer to Python is faster than PyArrow's Python layer.

### In Python (everything else)

STAC search, config management, output formatting, CLI dispatch, pipeline execution, COG metadata parsing, Zarr operations. The development speed advantage outweighs the runtime difference for these operations.

### Fallback Pattern

Every function accelerated by Rust must have a pure-Python fallback:
```python
try:
    from terraforge_rs import detect_format_fast
except ImportError:
    from terraforge.core._formats_py import detect_format_fast
```

`pip install terraforge` always works. Rust acceleration is a bonus.

## Alternatives Considered

- **Rust for everything** — Rejected. Shrinks contributor pool dramatically. Most TerraForge logic is I/O orchestration where Python is fast enough.
- **No Rust** — Rejected. The three identified bottlenecks have measurable Python overhead. Format detection across 10K files and parallel range reads for large COGs are real production workflows.
- **C extensions instead of Rust** — Rejected. PyO3/maturin has better DX, memory safety, and ecosystem momentum than CPython C extensions.

## Consequences

- Build requires Rust toolchain for extension development, but NOT for library usage (fallback exists)
- CI needs cibuildwheel for cross-platform wheel generation (manylinux, macOS arm64/x86_64, Windows)
- `packages/rs/pyproject.toml` uses maturin build backend — never hatchling
- Pure-Python fallback tests must run in CI to ensure they stay functional as Rust implementations evolve
