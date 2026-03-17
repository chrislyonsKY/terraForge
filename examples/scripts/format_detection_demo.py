"""Format detection matrix — testing detection across file types.

Generates a visual matrix showing EarthForge's format detection results
across multiple file types, with detection method and confidence.

Output: examples/outputs/format_detection_matrix.png

Usage::

    python examples/scripts/format_detection_demo.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "packages/core/src")

from earthforge.core.palettes import SET2

OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "format_detection_matrix.png"
OUTPUT_TXT = OUTPUT_DIR / "format_detection_matrix.txt"

# Test cases: (description, extension, magic_bytes_hex, expected_format)
TEST_CASES = [
    ("GeoTIFF (LE)", ".tif", "49492a00", "geotiff"),
    ("GeoTIFF (BE)", ".tif", "4d4d002a", "geotiff"),
    ("BigTIFF", ".tif", "49492b00", "geotiff"),
    ("Apache Parquet", ".parquet", "50415231", "parquet"),
    ("HDF5 / NetCDF-4", ".nc", "894844460d0a1a0a", "hdf5"),
    ("NetCDF Classic", ".nc", "43444601", "netcdf"),
    ("FlatGeobuf", ".fgb", "66676203", "flatgeobuf"),
    ("GeoJSON", ".geojson", "7b", "json"),
    ("Shapefile", ".shp", "0000270a", "shapefile"),
    ("LAS/LAZ", ".laz", "4c415346", "las"),
    ("PNG Image", ".png", "89504e47", "png"),
    ("JPEG Image", ".jpg", "ffd8ff", "jpeg"),
]


def main() -> None:
    """Generate format detection matrix."""
    print("EarthForge — Format Detection Matrix")
    print("=" * 45)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    # Run detection on synthetic test files
    tmp_dir = Path("examples/outputs/.tmp_detect")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for desc, ext, magic_hex, expected in TEST_CASES:
        magic = bytes.fromhex(magic_hex)
        test_file = tmp_dir / f"test{ext}"
        test_file.write_bytes(magic + b"\x00" * 100)

        from earthforge.core.formats import detect_sync

        try:
            detected = detect_sync(str(test_file))
            det_str = detected.value if hasattr(detected, "value") else str(detected)
            match = expected.lower() in det_str.lower()
        except Exception:
            det_str = "error"
            match = False

        method = "magic bytes" if len(magic) > 1 else "extension"
        results.append((desc, ext, det_str, method, match))
        status = "[PASS]" if match else "[MISS]"
        print(f"  {status} {desc:20s} -> {det_str}")

    # Clean up
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Render matrix
    print("\nRendering matrix...")
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.axis("off")

    headers = ["File Type", "Extension", "Detected As", "Method", "Status"]
    col_widths = [0.22, 0.10, 0.22, 0.14, 0.10]
    col_x = [0.02]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)

    # Header row
    y = 0.95
    for i, header in enumerate(headers):
        ax.text(
            col_x[i], y, header,
            fontsize=11, fontweight="bold",
            transform=ax.transAxes, verticalalignment="top",
        )
    y -= 0.04
    ax.axhline(y=y * ax.get_position().height, color="gray", linewidth=0.5)

    # Data rows
    set2_rgb = [
        tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
        for h in SET2
    ]
    pass_color = set2_rgb[0]  # teal
    miss_color = set2_rgb[1]  # orange

    for desc, ext, detected, method, match in results:
        y -= 0.06
        color = pass_color if match else miss_color
        status = "[PASS]" if match else "[MISS]"
        row = [desc, ext, detected, method, status]
        for i, val in enumerate(row):
            ax.text(
                col_x[i], y, val,
                fontsize=9, color="black" if i < 4 else color,
                fontweight="bold" if i == 4 else "normal",
                transform=ax.transAxes, verticalalignment="top",
            )

    ax.set_title(
        "EarthForge Format Detection Matrix\n"
        "Magic Bytes + Extension Detection Chain",
        fontsize=14, fontweight="bold", pad=20,
    )

    pass_count = sum(1 for *_, m in results if m)
    total = len(results)
    fig.text(
        0.5, 0.01,
        f"{pass_count}/{total} formats detected | "
        f"Palette: ColorBrewer Set2 | "
        f"EarthForge v1.0.0 | "
        f"{datetime.now(UTC).strftime('%Y-%m-%d')}",
        ha="center", fontsize=8, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: Format detection matrix showing EarthForge's ability to "
        f"identify {total} geospatial file formats by magic bytes and extension. "
        f"{pass_count} of {total} formats correctly detected. Results displayed "
        f"in a table with [PASS] in teal and [MISS] in orange (ColorBrewer Set2).\n\n"
        f"Data Source: Synthetic test files with known magic byte signatures\n"
        f"Access Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/format_detection_demo.py\n"
        f"Parameters: {total} file type test cases\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
