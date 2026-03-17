# DEM & Terrain Analysis

Elevation data from Copernicus DEM, SRTM, and OpenTopography.

## Grand Canyon {#grand-canyon}

1,844m of relief from the Colorado River to the rim.

![Grand Canyon DEM](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/opentopo_grand_canyon_dem.png)

**Run it:**
```bash
export OPENTOPO_API_KEY=your_key_here
python examples/scripts/opentopo_grand_canyon_demo.py
```

**What it demonstrates:**
- OpenTopography API integration (SRTM GL1 30m)
- Hillshade computation with configurable sun position
- Elevation cross-section profile
- High-contrast annotation lines (WCAG 2.1 AA)

## Swiss Alps — Matterhorn {#swiss-alps}

Alpine terrain from Copernicus DEM 30m with statistics sidebar.

![Swiss Alps DEM](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/opentopo_swiss_alps_dem.png)

**Run it:**
```bash
export OPENTOPO_API_KEY=your_key_here
python examples/scripts/opentopo_swiss_alps_demo.py
```

## Hawaii Volcanoes {#hawaii}

Kilauea and Mauna Loa volcanic terrain.

![Hawaii Volcano DEM](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/opentopo_hawaii_volcano.png)

**Run it:**
```bash
export OPENTOPO_API_KEY=your_key_here
python examples/scripts/opentopo_hawaii_volcano_demo.py
```

## Denali, Alaska — DEM Statistics {#denali}

Elevation histogram and statistics from the Alaska Range.

![Denali DEM Stats](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/dem_stats_denali_alaska.png)

**Run it:**
```bash
python examples/scripts/stac_copdem_alaska_demo.py
```
