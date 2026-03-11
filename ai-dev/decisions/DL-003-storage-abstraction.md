# DL-003: obstore Over fsspec for Storage Abstraction

**Date:** 2026-03-10
**Status:** Accepted
**Author:** Chris Lyons

## Context

TerraForge needs a unified interface for reading and writing data across S3, GCS, Azure Blob Storage, and local filesystem. Two dominant options exist in the Python ecosystem: `fsspec` (Python-native, widely adopted in PyData) and `obstore` (Rust-backed Python bindings for Apache `object-store`).

## Decision

Use `obstore` (object-store-python) as the storage abstraction layer, wrapped by `terraforge.core.storage`. No package should import obstore directly.

## Alternatives Considered

- **fsspec** — Rejected for this project. Broader ecosystem adoption and more backends (FTP, HDFS, in-memory), but: (1) Python-native I/O is slower for large transfers and parallel range reads, (2) auth is a `**kwargs` passthrough with no type safety, (3) dependency tree is heavier (pulls aiohttp, requests, and backend packages), (4) no zero-copy Arrow integration.
- **Raw boto3/google-cloud-storage/azure-storage-blob** — Rejected. Three separate SDKs with three different auth models. The purpose of a storage abstraction is to avoid this.
- **Custom abstraction over httpx** — Rejected. Reimplementing S3 signature V4, GCS OAuth, and Azure SAS token handling is not a good use of development time.

## Consequences

- Rust-backed I/O performance for range reads and large transfers
- Zero-copy Arrow integration benefits GeoParquet workflows (Parquet → Arrow without Python memory copies)
- Narrower backend coverage than fsspec — S3, GCS, Azure, and local FS only. No FTP, HDFS, or in-memory. This is sufficient for TerraForge's cloud-native scope.
- Users with private S3-compatible stores (MinIO, Ceph) can configure via S3-compatible endpoint URLs in profiles
- obstore is newer and less battle-tested than fsspec — monitor for edge cases in auth and error handling
