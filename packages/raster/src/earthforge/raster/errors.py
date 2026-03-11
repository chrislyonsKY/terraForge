"""Raster-specific error types."""

from __future__ import annotations

from earthforge.core.errors import EarthForgeError


class RasterError(EarthForgeError):
    """Base exception for raster operations.

    Parameters:
        message: Human-readable description.
        exit_code: CLI exit code (defaults to ``10``).
    """

    def __init__(self, message: str, *, exit_code: int = 10) -> None:
        super().__init__(message, exit_code=exit_code)


class CogValidationError(RasterError):
    """Raised when a file fails COG compliance checks.

    Parameters:
        message: Human-readable description of the validation failure.
        exit_code: CLI exit code (defaults to ``11``).
    """

    def __init__(self, message: str, *, exit_code: int = 11) -> None:
        super().__init__(message, exit_code=exit_code)
