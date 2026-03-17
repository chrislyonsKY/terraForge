"""Seasonal vegetation change visualization — NDVI time series to animated GIF.

Demonstrates a remote sensing workflow: computing NDVI (Normalized Difference
Vegetation Index) from Sentinel-2 bands across multiple dates and assembling
the results into an animated GIF showing seasonal greenup and senescence.

NDVI = (NIR - Red) / (NIR + Red)
  - Values near 1.0 = dense green vegetation
  - Values near 0.0 = bare soil, water, urban
  - Values < 0 = water bodies, snow

Workflow:
  1. Search STAC for low-cloud Sentinel-2 scenes across the growing season
  2. For each scene, read a small window of the Red and NIR bands (via HTTP
     range requests — no full download)
  3. Compute NDVI for each date
  4. Render each NDVI array as a colorized frame
  5. Assemble frames into an animated GIF

Output: data/vegetation_change.gif

Requirements: numpy, Pillow (pip install numpy Pillow)
Data source: Element84 Earth Search (public, no auth)

Usage::

    python examples/scripts/vegetation_change_gif.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/raster/src")
sys.path.insert(0, "packages/stac/src")

from earthforge.core.config import EarthForgeProfile
from earthforge.stac.search import search_catalog

STAC_API = "https://earth-search.aws.element84.com/v1"

# Study area: small window in Central Kentucky (Bluegrass farmland)
# We read a small spatial window to keep downloads fast
STUDY_BBOX = [-84.55, 38.00, -84.45, 38.08]

# Search across a full growing season — one scene per month ideally
DATE_RANGE = "2025-04-01/2025-10-31"
MAX_CLOUD = 25.0

# Output
OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PATH = OUTPUT_DIR / "vegetation_change.gif"

# NDVI color ramp: colorblind-safe BrBG diverging palette (WCAG 2.1 AA)
# Derived from earthforge.core.palettes.DIVERGING_BRBG
# Each entry is (ndvi_threshold, R, G, B)
NDVI_COLORMAP = [
    (-1.0, 20, 20, 80),  # water / shadow — dark blue
    (-0.1, 140, 81, 10),  # bare soil — brown (#8c510a)
    (0.0, 191, 129, 45),  # sparse — tan (#bf812d)
    (0.15, 223, 194, 125),  # transition — light brown (#dfc27d)
    (0.3, 245, 245, 245),  # midpoint — near white (#f5f5f5)
    (0.5, 128, 205, 193),  # moderate vegetation — light teal (#80cdc1)
    (0.7, 53, 151, 143),  # dense vegetation — teal (#35978f)
    (1.0, 1, 102, 94),  # very dense — dark teal (#01665e)
]


def ndvi_to_rgb(ndvi: np.ndarray) -> np.ndarray:
    """Map NDVI values to RGB using a vegetation color ramp.

    Parameters:
        ndvi: 2D array of NDVI values (-1 to 1).

    Returns:
        3D uint8 array (H, W, 3) of RGB values.
    """
    h, w = ndvi.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(len(NDVI_COLORMAP) - 1):
        lo_val, lo_r, lo_g, lo_b = NDVI_COLORMAP[i]
        hi_val, hi_r, hi_g, hi_b = NDVI_COLORMAP[i + 1]

        mask = (ndvi >= lo_val) & (ndvi < hi_val)
        if not np.any(mask):
            continue

        # Linear interpolation within this segment
        t = (ndvi[mask] - lo_val) / (hi_val - lo_val)
        t = np.clip(t, 0, 1)

        rgb[mask, 0] = (lo_r + t * (hi_r - lo_r)).astype(np.uint8)
        rgb[mask, 1] = (lo_g + t * (hi_g - lo_g)).astype(np.uint8)
        rgb[mask, 2] = (lo_b + t * (hi_b - lo_b)).astype(np.uint8)

    # Handle values at the upper boundary
    mask = ndvi >= NDVI_COLORMAP[-1][0]
    if np.any(mask):
        rgb[mask] = NDVI_COLORMAP[-1][1:]

    return rgb


def add_label(rgb: np.ndarray, text: str) -> np.ndarray:
    """Burn a simple text label into the top-left corner of an RGB image.

    Uses a basic pixel font approach — no external font dependencies.
    If Pillow's ImageDraw is available, uses that for nicer text.

    Parameters:
        rgb: 3D uint8 array (H, W, 3).
        text: Label text to render.

    Returns:
        Modified RGB array with label.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(img)

        # Semi-transparent background bar
        bar_height = 28
        for y in range(bar_height):
            for x in range(min(len(text) * 10 + 16, rgb.shape[1])):
                r, g, b = rgb[y, x]
                rgb[y, x] = [r // 3, g // 3, b // 3]

        img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = ImageFont.load_default()

        draw.text((8, 4), text, fill=(255, 255, 255), font=font)
        return np.array(img)
    except ImportError:
        # Fallback: just darken the top bar
        bar_height = 20
        rgb[:bar_height, : min(len(text) * 8 + 16, rgb.shape[1])] //= 3
        return rgb


async def read_band_window(href: str, bbox: list[float]) -> np.ndarray | None:
    """Read a spatial window from a remote COG band via rasterio.

    Uses GDAL's /vsicurl/ virtual filesystem to read only the tiles
    that intersect the bounding box — typically a few hundred KB
    instead of the full 100+ MB band file.

    Parameters:
        href: URL to the COG band file.
        bbox: Bounding box [west, south, east, north] in the raster's CRS.

    Returns:
        2D numpy array of band values, or None if read fails.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds

        with rasterio.open(href) as ds:
            window = from_bounds(*bbox, transform=ds.transform)
            data = ds.read(1, window=window)
            return data.astype(np.float32)
    except Exception as exc:
        print(f"    Failed to read {href.split('/')[-1]}: {exc}")
        return None


async def main() -> None:
    """Run the vegetation change GIF pipeline."""
    print()
    print("=" * 60)
    print("  EarthForge — Seasonal Vegetation Change GIF")
    print("  NDVI Time Series Animation")
    print("=" * 60)
    print()

    profile = EarthForgeProfile(name="earth-search", stac_api=STAC_API)

    # Step 1: Search for clear Sentinel-2 scenes
    print("STEP 1: Search for clear Sentinel-2 scenes")
    print("-" * 45)
    result = await search_catalog(
        profile,
        collections=["sentinel-2-l2a"],
        bbox=STUDY_BBOX,
        datetime_range=DATE_RANGE,
        max_items=50,
    )

    # Filter by cloud cover and pick one scene per month
    candidates = [
        item for item in result.items if (item.properties.get("eo:cloud_cover") or 100) < MAX_CLOUD
    ]
    candidates.sort(key=lambda i: i.datetime or "")

    # Deduplicate: keep the clearest scene per month
    monthly_best: dict[str, object] = {}
    for item in candidates:
        month = (item.datetime or "")[:7]
        if not month:
            continue
        existing = monthly_best.get(month)
        if existing is None or (
            item.properties.get("eo:cloud_cover", 100)
            < existing.properties.get("eo:cloud_cover", 100)
        ):
            monthly_best[month] = item

    scenes = sorted(monthly_best.values(), key=lambda i: i.datetime or "")
    print(f"  Total scenes found: {len(result.items)}")
    print(f"  Clear (<{MAX_CLOUD}% cloud): {len(candidates)}")
    print(f"  Selected (1/month): {len(scenes)}")

    if len(scenes) < 2:
        print("  Not enough clear scenes for animation. Try a different date range.")
        return

    for item in scenes:
        cc = item.properties.get("eo:cloud_cover", "?")
        print(f"    {item.datetime[:10]}  cloud={cc}%  {item.id}")
    print()

    # Step 2: Compute NDVI for each scene
    print("STEP 2: Compute NDVI per scene")
    print("-" * 45)

    frames = []
    frame_labels = []

    for item in scenes:
        date_str = (item.datetime or "unknown")[:10]
        print(f"  Processing {date_str}...")

        # Find Red (B04) and NIR (B08) bands
        red_asset = next((a for a in item.assets if a.key in ("red", "B04")), None)
        nir_asset = next((a for a in item.assets if a.key in ("nir", "B08")), None)

        if not red_asset or not nir_asset:
            print("    Skipping — missing red/NIR bands")
            continue

        # Read spatial windows from remote COGs
        print("    Reading Red band (range request)...")
        red = await read_band_window(red_asset.href, STUDY_BBOX)

        print("    Reading NIR band (range request)...")
        nir = await read_band_window(nir_asset.href, STUDY_BBOX)

        if red is None or nir is None:
            continue

        # Ensure same shape (NIR and Red should match for Sentinel-2)
        min_h = min(red.shape[0], nir.shape[0])
        min_w = min(red.shape[1], nir.shape[1])
        red = red[:min_h, :min_w]
        nir = nir[:min_h, :min_w]

        # Compute NDVI
        denominator = nir + red
        ndvi = np.where(denominator > 0, (nir - red) / denominator, 0)
        ndvi = np.clip(ndvi, -1, 1)

        mean_ndvi = np.nanmean(ndvi)
        print(f"    NDVI: mean={mean_ndvi:.3f}  shape={ndvi.shape}")

        # Colorize
        rgb = ndvi_to_rgb(ndvi)
        label = f"{date_str}  NDVI={mean_ndvi:.2f}"
        rgb = add_label(rgb, label)

        frames.append(rgb)
        frame_labels.append(label)

    print()

    if len(frames) < 2:
        print("Not enough valid frames to create animation.")
        return

    # Step 3: Assemble GIF
    print("STEP 3: Create animated GIF")
    print("-" * 45)

    try:
        from PIL import Image

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Convert numpy arrays to PIL Images
        pil_frames = [Image.fromarray(f) for f in frames]

        # Save as animated GIF
        pil_frames[0].save(
            str(OUTPUT_PATH),
            save_all=True,
            append_images=pil_frames[1:],
            duration=800,  # ms per frame
            loop=0,  # infinite loop
        )

        file_size = OUTPUT_PATH.stat().st_size
        print(f"  Output:     {OUTPUT_PATH}")
        print(f"  Frames:     {len(frames)}")
        print(f"  Frame size: {frames[0].shape[1]}x{frames[0].shape[0]} px")
        print(f"  Duration:   {len(frames) * 800}ms ({len(frames) * 0.8:.1f}s)")
        print(f"  File size:  {file_size:,} bytes")
        print()

        # Also save individual frames as PNG for inspection
        for i, (frame, _label) in enumerate(zip(pil_frames, frame_labels, strict=True)):
            frame_path = OUTPUT_DIR / f"ndvi_frame_{i:02d}.png"
            frame.save(str(frame_path))

        print(f"  Individual frames saved to {OUTPUT_DIR}/ndvi_frame_*.png")

    except ImportError:
        print("  Pillow not installed. Install with: pip install Pillow")
        print("  Saving raw NDVI arrays as .npy files instead...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            np.save(str(OUTPUT_DIR / f"ndvi_frame_{i:02d}.npy"), frame)

    print()
    print("Vegetation change GIF complete.")
    print()
    print("Legend:")
    print("  Dark blue  = water/shadow (NDVI < -0.1)")
    print("  Brown/tan  = bare soil (NDVI 0.0-0.15)")
    print("  Yellow     = sparse vegetation (NDVI 0.15-0.3)")
    print("  Light green= moderate vegetation (NDVI 0.3-0.5)")
    print("  Dark green = dense vegetation (NDVI 0.7+)")


if __name__ == "__main__":
    asyncio.run(main())
