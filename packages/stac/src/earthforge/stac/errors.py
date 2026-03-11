"""STAC-specific error types.

All exceptions inherit from :class:`~earthforge.core.errors.EarthForgeError`
so the CLI can catch them uniformly and map to appropriate exit codes.
"""

from __future__ import annotations

from earthforge.core.errors import EarthForgeError


class StacError(EarthForgeError):
    """Base error for STAC operations.

    Parameters:
        message: Human-readable error description.
        exit_code: Process exit code (default: 30).
    """

    def __init__(self, message: str, *, exit_code: int = 30) -> None:
        super().__init__(message, exit_code=exit_code)


class StacSearchError(StacError):
    """Error during a STAC catalog search.

    Parameters:
        message: Human-readable error description.
        exit_code: Process exit code (default: 31).
    """

    def __init__(self, message: str, *, exit_code: int = 31) -> None:
        super().__init__(message, exit_code=exit_code)
