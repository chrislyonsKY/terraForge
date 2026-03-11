"""EarthForge error hierarchy.

All exceptions raised by EarthForge inherit from ``EarthForgeError``. Each domain
package defines its own subclasses (e.g. ``StacSearchError``, ``CogValidationError``)
so callers can catch at whatever granularity they need. The ``exit_code`` attribute
maps directly to CLI exit codes, letting the CLI layer translate library exceptions
into meaningful shell return values without parsing message strings.
"""

from __future__ import annotations


class EarthForgeError(Exception):
    """Base exception for all EarthForge errors.

    Parameters:
        message: Human-readable description of the error.
        exit_code: CLI exit code to use when this error propagates to the shell.
                   Defaults to ``1`` (general error).

    Attributes:
        exit_code: The numeric exit code for CLI propagation.
    """

    exit_code: int = 1

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(EarthForgeError):
    """Raised when configuration loading, parsing, or validation fails.

    Examples: missing config file, invalid TOML, unknown profile name,
    missing required field in a profile.
    """

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message, exit_code=exit_code)


class StorageError(EarthForgeError):
    """Raised when a cloud storage operation fails.

    Examples: permission denied on S3, object not found, network timeout,
    invalid storage backend name.
    """

    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message, exit_code=exit_code)


class HttpError(EarthForgeError):
    """Raised when an HTTP request fails after retries.

    Parameters:
        message: Human-readable description.
        status_code: The HTTP status code that triggered the error, if available.
        exit_code: CLI exit code (defaults to ``4``).

    Attributes:
        status_code: The HTTP status code, or ``None`` for connection-level failures.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        exit_code: int = 4,
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.status_code = status_code


class FormatDetectionError(EarthForgeError):
    """Raised when format detection cannot determine the file type.

    This typically means the file's magic bytes don't match any known format,
    the extension is unrecognized, and content inspection was inconclusive.
    """

    def __init__(self, message: str, *, exit_code: int = 5) -> None:
        super().__init__(message, exit_code=exit_code)
