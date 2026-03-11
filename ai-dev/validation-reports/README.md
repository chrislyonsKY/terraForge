# ai-dev/validation-reports/

Real-world validation results. Each report documents the actual behavior of a EarthForge feature against the real-world test datasets defined in `ai-dev/test-data-plan.md`.

**A feature is not complete until its validation report is committed.**

## Report Naming

`VR-{milestone}-{feature}.md`

Examples:
- `VR-M0-format-detection.md`
- `VR-M0-raster-info.md`
- `VR-M1-stac-search.md`
- `VR-M1-raster-preview.md`
- `VR-M2-vector-query.md`
- `VR-M2-raster-convert.md`

## Report Template

```markdown
# Validation Report: {Feature Name}

**Milestone:** M{n}
**Date:** YYYY-MM-DD
**Tester:** {name}
**EarthForge version:** {commit hash or version}

## Test Environment

- OS: {e.g., Ubuntu 24.04, macOS 15}
- Python: {version}
- Network: {approximate bandwidth, e.g., "100 Mbps fiber"}
- Relevant packages: {rasterio version, geopandas version, etc.}

## Test Results

### Test 1: {Description}

**Dataset:** {name and URL from test-data-plan.md}
**Command:**
```bash
earthforge {exact command run}
```

**Expected result:** {what should happen}

**Actual result:**
```
{paste actual output, truncated if >50 lines}
```

**Status:** PASS / FAIL / PARTIAL
**Duration:** {wall clock time}
**Data transferred:** {if measurable, e.g., "1.2MB range reads for a 150MB COG"}
**Notes:** {any unexpected behavior, warnings, edge cases}

### Test 2: {Description}

{repeat for each test case}

## Third-Party Validation

{For conversion features: output validated by external tools}

**Tool:** {e.g., rio cogeo validate}
**Command:**
```bash
{exact command}
```
**Result:**
```
{paste output}
```

## Performance Observations

| Operation | Target (from test-data-plan.md) | Actual | Status |
|---|---|---|---|
| {operation} | {target time} | {measured time} | MET / MISSED |

## Issues Found

{List any bugs, edge cases, or unexpected behavior discovered during validation. Reference GitHub issues if filed.}

- [ ] {Issue description} — {filed as #N / fixed in commit abc123 / deferred}

## Conclusion

{One paragraph: does this feature work correctly against real-world data? Any caveats?}
```
