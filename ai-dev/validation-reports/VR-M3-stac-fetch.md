# VR-M3-stac-fetch — STAC Asset Fetch Validation

**Date:** 2026-03-12
**Module:** `earthforge.stac.fetch`
**Data Source:** KyFromAbove STAC API — `orthos-phase3` collection

---

## Command

```python
result = await fetch_assets(
    profile,
    item_url="https://spved5ihrl.execute-api.us-west-2.amazonaws.com/collections/orthos-phase3/items/N097E305_2024_Season1_3IN_cog.tif",
    output_dir="data/kyfromabove_fetch/N097E305_2024_Season1_3IN_cog.tif",
    assets=["thumbnail"],
    parallel=2,
)
```

## Item

| Field | Value |
|-------|-------|
| Item ID | `N097E305_2024_Season1_3IN_cog.tif` |
| Collection | `orthos-phase3` |
| Datetime | 2024-02-01 |
| Assets | data (COG), metadata (TXT), thumbnail (PNG) |

## Fetch Result (First Run)

| Field | Value |
|-------|-------|
| Assets requested | 1 (thumbnail) |
| Assets downloaded | 1 |
| Assets skipped | 0 |
| Bytes downloaded | 78,026 |
| Elapsed | 2.34s |

File written: `N097E305_2024_Season1_3IN_cog.png` (78,026 bytes)

## Resume Test (Second Run)

Re-ran fetch against the same item and output directory.

| Field | Value |
|-------|-------|
| Assets requested | 1 |
| Assets downloaded | 0 |
| Assets skipped | 1 |
| Bytes downloaded | 0 |

Resume mechanism confirmed: HEAD request returned `Content-Length: 78026`, local
file size matched, download skipped without re-transferring data.

## Notes

- `orthos-phase3` 3-inch COG assets are several hundred MB each. Thumbnail was
  used for demo bandwidth. The fetch path is identical for COG assets — streaming
  in 64 KB chunks to avoid memory pressure.
- Item URL is constructed from the STAC API base + collection + item ID. A future
  enhancement could accept a STAC item URL directly from a prior `stac search`
  JSON output (pipeline composition).
- Full COG fetch: remove the `assets=["thumbnail"]` filter to download the data
  asset and test large-file streaming.
