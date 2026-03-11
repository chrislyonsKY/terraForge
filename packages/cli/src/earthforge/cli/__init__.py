"""EarthForge CLI — thin dispatch layer for cloud-native geospatial operations.

This package contains NO business logic. Every command handler parses arguments,
calls an async library function via ``asyncio.run()``, and passes the result to
the output renderer. That's it.
"""
