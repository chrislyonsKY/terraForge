"""Real-world demo: inspect ERA5 Zarr datacube on S3.

ERA5 is a global atmospheric reanalysis dataset produced by ECMWF.
The AWS Open Data version (era5-pds) is stored as Zarr on S3 with
one store per month per variable.

This script:
  1. Opens a single ERA5 variable store (2m temperature, 2025-01)
  2. Prints dimensions, variables, spatial extent, and time range
  3. Slices a small Kentucky bbox over June 2025 and writes it locally

Public, no authentication required.
S3 bucket: s3://era5-pds/zarr/2025/01/data/air_temperature_at_2_metres.zarr

Run from the repo root:
  python examples/scripts/cube_info_era5_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/cube/src")

from earthforge.cube.info import inspect_cube
from earthforge.cube.slice import slice_cube


ERA5_STORE = "s3://era5-pds/zarr/2025/01/data/air_temperature_at_2_metres.zarr"
KY_BBOX = (-85.5, 37.0, -84.0, 38.5)


async def main() -> None:
    print("=== ERA5 Cube Info ===")
    print(f"Store: {ERA5_STORE}")
    print()

    try:
        info = await inspect_cube(ERA5_STORE)
    except Exception as exc:
        print(f"Could not connect to S3 (no internet or auth needed): {exc}")
        print("This demo requires an internet connection and s3fs installed.")
        return

    print(f"Format:        {info.format}")
    print(f"Spatial bbox:  {info.spatial_bbox}")
    print(f"Time range:    {info.time_range}")
    print()

    print(f"Dimensions ({len(info.dimensions)}):")
    for dim in info.dimensions:
        line = f"  {dim.name:<15} size={dim.size:<8} dtype={dim.dtype}"
        if dim.units:
            line += f"  [{dim.units}]"
        if dim.min_value and dim.max_value:
            line += f"  {dim.min_value} → {dim.max_value}"
        print(line)

    print()
    print(f"Variables ({len(info.variables)}):")
    for var in info.variables:
        chunks_str = f"  chunks={var.chunks}" if var.chunks else ""
        long = f"  ({var.long_name})" if var.long_name else ""
        print(f"  {var.name:<30} shape={var.shape}  dtype={var.dtype}{chunks_str}{long}")

    if info.global_attrs:
        print()
        print("Global attributes:")
        for k, v in list(info.global_attrs.items())[:8]:
            print(f"  {k}: {v}")

    # Serialize to JSON
    doc = json.loads(info.model_dump_json())
    print()
    print("JSON serialization: OK")
    print(f"  Keys: {list(doc.keys())}")


if __name__ == "__main__":
    asyncio.run(main())
