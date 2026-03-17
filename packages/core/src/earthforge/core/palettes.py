"""Colorblind-safe palette constants for EarthForge visualizations.

All palettes are verified safe for the three main forms of color vision
deficiency (deuteranopia, protanopia, tritanopia).  Every visualization
produced by EarthForge — CLI preview images, example output maps, and
documentation figures — must use one of these palettes.

Palette categories:

- **Sequential** — for continuous data with a single direction (elevation,
  temperature, NDVI magnitude).  ``viridis`` and ``cividis`` are
  perceptually uniform and safe for all forms of CVD.

- **Diverging** — for data centered on a meaningful midpoint (NDVI
  gain/loss, temperature anomalies).  Brown → white → teal, sourced from
  ColorBrewer ``BrBG``.

- **Categorical** — for discrete classes (land cover types, format
  categories).  ColorBrewer ``Set2`` (8 colors) and ``Paired`` (12 colors).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sequential palettes — perceptually uniform, CVD-safe
# ---------------------------------------------------------------------------

VIRIDIS: list[str] = [
    "#440154", "#482777", "#3e4a89", "#31688e", "#26838e",
    "#1f9e89", "#6cce5a", "#b6de2b", "#fee825",
]
"""Viridis 9-stop palette — dark purple to bright yellow."""

CIVIDIS: list[str] = [
    "#00224e", "#123570", "#3b496c", "#575d6d", "#707173",
    "#8a8678", "#a59c74", "#c3b369", "#e1cc55",
]
"""Cividis 9-stop palette — dark blue to warm yellow, optimized for CVD."""

# ---------------------------------------------------------------------------
# Diverging palette — centered on white midpoint
# ---------------------------------------------------------------------------

DIVERGING_BRBG: list[str] = [
    "#8c510a", "#bf812d", "#dfc27d", "#f6e8c3",
    "#f5f5f5",
    "#c7eae5", "#80cdc1", "#35978f", "#01665e",
]
"""Brown → white → teal diverging palette (9 stops, ColorBrewer BrBG)."""

# ---------------------------------------------------------------------------
# Categorical palettes — discrete classes
# ---------------------------------------------------------------------------

SET2: list[str] = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3",
]
"""ColorBrewer Set2 — 8 qualitative colors, CVD-safe."""

PAIRED: list[str] = [
    "#a6cee3", "#1f78b4", "#b2df8a", "#33a02c",
    "#fb9a99", "#e31a1c", "#fdbf6f", "#ff7f00",
    "#cab2d6", "#6a3d9a", "#ffff99", "#b15928",
]
"""ColorBrewer Paired — 12 qualitative colors, grouped in light/dark pairs."""

# ---------------------------------------------------------------------------
# Convenience groupings
# ---------------------------------------------------------------------------

SEQUENTIAL: dict[str, list[str]] = {
    "viridis": VIRIDIS,
    "cividis": CIVIDIS,
}
"""All sequential palettes by name."""

DIVERGING: dict[str, list[str]] = {
    "brbg": DIVERGING_BRBG,
}
"""All diverging palettes by name."""

CATEGORICAL: dict[str, list[str]] = {
    "set2": SET2,
    "paired": PAIRED,
}
"""All categorical palettes by name."""
