"""Cube-domain error types for EarthForge.

All exceptions in this module inherit from :class:`earthforge.core.errors.EarthForgeError`
so callers can catch either the base class or the specific subclass.
"""

from earthforge.core.errors import EarthForgeError


class CubeError(EarthForgeError):
    """Raised when a datacube operation fails.

    Covers format errors (not a valid Zarr/NetCDF store), I/O failures,
    missing variables, and invalid slice parameters.
    """
