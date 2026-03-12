"""EarthForge declarative pipeline runner.

Executes geospatial workflows defined as YAML documents. A pipeline
describes a data source (typically a STAC search), a sequence of processing
steps, and an output specification. Steps run concurrently per STAC item
via ``asyncio.TaskGroup``.

Pipeline YAML schema::

    pipeline:
      name: my-workflow
      source:
        stac_search:
          api: https://earth-search.aws.element84.com/v1
          collection: sentinel-2-l2a
          bbox: [-85.5, 37.0, -84.0, 38.5]
          datetime: "2025-06-01/2025-06-30"
          query:
            eo:cloud_cover: {lt: 20}
          limit: 3
      steps:
        - for_each_item:
            - raster.calc:
                expression: "(B08 - B04) / (B08 + B04)"
                output: "ndvi_{item_id}.tif"
            - raster.convert:
                format: COG
                compression: deflate
"""
