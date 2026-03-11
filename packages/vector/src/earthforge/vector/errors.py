"""Vector-specific error types.

All exceptions inherit from :class:`~earthforge.core.errors.EarthForgeError`
so the CLI can catch them uniformly and map to appropriate exit codes.
"""

from __future__ import annotations

from earthforge.core.errors import EarthForgeError


class VectorError(EarthForgeError):
    """Base error for vector operations.

    Parameters:
        message: Human-readable error description.
        exit_code: Process exit code (default: 20).
    """

    def __init__(self, message: str, *, exit_code: int = 20) -> None:
        super().__init__(message, exit_code=exit_code)
