"""EarthForge vector format inspection.

Provides deep metadata extraction for vector geospatial formats including
GeoParquet, FlatGeobuf, and GeoJSON. Uses pyarrow for Parquet/GeoParquet
introspection without loading full datasets into memory.
"""
