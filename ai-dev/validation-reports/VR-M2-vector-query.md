# VR-M2-vector-query — Vector Spatial Query Validation

**Date:** 2026-03-12
**Module:** `earthforge.vector.query`
**Data:** Synthetic KY cities GeoParquet (6 point features, from VR-M2-vector-convert)

---

## Query 1 — Full dataset (no bbox)

```
query_features("cities.parquet")
```

**Result:** 6 features returned, `bbox_filter = None`

## Query 2 — Eastern KY bbox

```
query_features("cities.parquet", bbox=(-84.0, 36.5, -82.0, 39.5))
```

Expected: Lexington (-84.495 is just outside west edge), Pikeville (-82.519)
Actual: **1 feature** (Pikeville) — Lexington correctly excluded at -84.495 lon

**Result:** 1 feature returned, `bbox_filter = [-84.0, 36.5, -82.0, 39.5]`

## Query 3 — Full KY bbox

```
query_features("cities.parquet", bbox=(-89.0, 36.0, -81.0, 40.0))
```

**Result:** 6 features returned — all cities within KY bounds

## Predicate Pushdown Behavior

The GeoParquet files produced by `convert_vector` include per-feature `bbox` covering metadata.
`_build_bbox_filter` detects this via the `geo` Parquet metadata and constructs a pyarrow filter
expression on the covering columns, enabling row-group skipping at the Parquet reader level.

When covering metadata is absent, the module falls back to reading all rows and post-filtering
on geometry. In this synthetic dataset (single row group, 6 features) both paths produce
identical results — the covering path was verified via the `bbox_filter` field being populated
in the result.

## Notes

- WKB point geometry parsing fallback (no shapely) confirmed working — coordinates
  extracted via `struct.unpack` from WKB bytes and used for containment check.
- `query_features` returns `total_rows` (pre-filter) and `feature_count` (post-filter)
  allowing callers to observe the pushdown ratio.
