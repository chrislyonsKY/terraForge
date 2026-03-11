# DL-002: Async-First I/O Architecture

**Date:** 2026-03-10
**Status:** Accepted
**Author:** Chris Lyons

## Context

TerraForge's primary operations are network I/O: STAC API search, COG range reads, cloud storage access, asset downloads. Sequential execution of these operations creates a performance ceiling that blocks adoption for batch workflows (processing hundreds of STAC items, generating previews for a collection).

## Decision

All I/O operations are implemented as async functions using `httpx.AsyncClient` for HTTP and `obstore` for cloud storage. The async API is the primary API. Synchronous wrappers are provided as a convenience layer for notebooks and simple scripts.

The CLI wraps async calls with `asyncio.run()` at the command entry point.

Naming convention: `search()` is async, `search_sync()` is the sync wrapper. The async version has no prefix because it is the primary interface.

## Alternatives Considered

- **Sync-first with threading** — Rejected. Threading in Python is limited by the GIL for CPU work and less efficient than async for I/O-bound work. The entire geospatial Python ecosystem is moving toward async (httpx, obstore, newer STAC clients).
- **Async-optional (both paths as peers)** — Rejected. Maintaining two parallel implementations is a maintenance burden and invites drift. One canonical path (async) with a thin wrapper (sync) is sustainable.
- **Trio instead of asyncio** — Rejected. asyncio is stdlib and universally supported. Trio's structured concurrency is elegant but ecosystem support is narrower. anyio could bridge both, but adds a dependency for marginal benefit.

## Consequences

- All library functions that perform I/O are `async def`
- The CLI layer uses `asyncio.run()` — Typer commands are sync functions that call async internals
- pystac-client is synchronous — wrap with `asyncio.to_thread()` until an async STAC client exists
- Test fixtures must handle async: `pytest-asyncio` with `asyncio_mode = "auto"`
- Sync wrappers exist for every public async function — the library is usable without async knowledge
