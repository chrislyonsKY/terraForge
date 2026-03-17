# NDVI Analysis

Normalized Difference Vegetation Index from Sentinel-2 satellite imagery.

## Colorado Front Range {#colorado-front-range}

Shows the vegetation gradient from plains to alpine tundra.

![NDVI Colorado Front Range](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/ndvi_colorado_front_range.png)

**Run it:**
```bash
python examples/scripts/sentinel2_colorado_ndvi_demo.py
```

**What it demonstrates:**
- STAC search with cloud cover filtering
- Windowed reads from remote COGs (no full download)
- CRS reprojection for bounding box queries
- BrBG colorblind-safe diverging palette

## Amazon Rainforest {#amazon}

Dense tropical canopy near Manaus, Brazil.

![NDVI Amazon](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/ndvi_amazon_manaus.png)

**Run it:**
```bash
python examples/scripts/sentinel2_amazon_ndvi_demo.py
```

## Netherlands — Rotterdam/Delft {#netherlands}

Urban, water, and agricultural land use classification by NDVI.

![NDVI Netherlands](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/ndvi_netherlands_rotterdam.png)

**Run it:**
```bash
python examples/scripts/sentinel2_netherlands_demo.py
```

## Pipeline Workflow {#pipeline}

Automated STAC-to-NDVI pipeline using the expression evaluator.

![Pipeline NDVI](https://raw.githubusercontent.com/chrislyonsKY/earthForge/main/examples/outputs/pipeline_ndvi_output.png)

**Run it:**
```bash
python examples/scripts/pipeline_ndvi_demo.py
```

**Pipeline steps:**
1. STAC search for clear Sentinel-2 scene
2. Range-read B04 (red) and B08 (NIR) bands
3. Compute NDVI via safe expression evaluator: `(B08 - B04) / (B08 + B04)`
4. Render with BrBG palette + pipeline summary sidebar
