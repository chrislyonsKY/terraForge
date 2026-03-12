"""Pipeline YAML template generator.

Generates a starter pipeline document that demonstrates the most common
STAC → process → COG workflow. The template includes inline comments
explaining each section.
"""

from __future__ import annotations

NDVI_TEMPLATE = """\
# EarthForge Pipeline — NDVI from Sentinel-2
#
# Run:   earthforge pipeline run ndvi_pipeline.yaml
# Check: earthforge pipeline validate ndvi_pipeline.yaml

pipeline:
  name: sentinel2-ndvi
  description: >
    Search Sentinel-2 L2A for clear scenes over a bounding box,
    compute NDVI, and convert outputs to COG.

  # Root directory for all outputs. Each item gets its own subdirectory:
  # output/<item_id>/ndvi_{item_id}.tif
  output_dir: ./output

  # Maximum concurrent item workers. Set to 1 for sequential execution.
  parallel: 4

  source:
    stac_search:
      api: https://earth-search.aws.element84.com/v1
      collection: sentinel-2-l2a
      bbox: [-85.5, 37.0, -84.0, 38.5]       # Kentucky
      datetime: "2025-06-01/2025-09-30"
      query:
        eo:cloud_cover:
          lt: 20                              # Max 20% cloud cover
      limit: 3

  steps:
    - for_each_item:
        # Step 1: Download the red (B04) and NIR (B08) bands
        - stac.fetch:
            assets: [B04, B08]
            parallel: 2

        # Step 2: Compute NDVI = (NIR - Red) / (NIR + Red)
        # Variable names must match the asset keys fetched above.
        # The expression uses a safe AST evaluator — no eval() or exec().
        - raster.calc:
            expression: "(B08 - B04) / (B08 + B04)"
            output: "ndvi_{item_id}.tif"
            dtype: float32

        # Step 3: Convert the result to a Cloud Optimized GeoTIFF
        - raster.convert:
            format: COG
            compression: deflate
            input: result           # "result" is the output key from raster.calc
            output: "ndvi_{item_id}_cog.tif"
"""


def get_template(template_name: str = "ndvi") -> str:
    """Return a starter pipeline YAML template.

    Parameters:
        template_name: Template identifier. Currently only ``"ndvi"``
            is built in.

    Returns:
        YAML string ready to write to a file.

    Raises:
        ValueError: If ``template_name`` is not recognized.
    """
    templates = {"ndvi": NDVI_TEMPLATE}
    if template_name not in templates:
        available = ", ".join(templates)
        raise ValueError(
            f"Unknown template '{template_name}'. Available: {available}"
        )
    return templates[template_name]
