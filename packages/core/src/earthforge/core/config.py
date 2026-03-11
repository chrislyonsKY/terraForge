"""EarthForge configuration management.

Provides profile-based configuration backed by a TOML file at
``~/.earthforge/config.toml``. Each profile bundles a STAC API endpoint,
a storage backend selection, and backend-specific options (credentials,
regions, endpoints). The ``default`` profile is used when no ``--profile``
flag is given.

Configuration file format::

    [profiles.default]
    stac_api = "https://earth-search.aws.element84.com/v1"
    storage = "s3"

    [profiles.default.storage_options]
    region = "us-west-2"

Functions:
    load_profile: Async loader that reads config and returns a typed profile.
    load_profile_sync: Convenience sync wrapper.
    init_config: Creates a starter config file with a default profile.
    config_dir: Returns the resolved config directory path.
"""

from __future__ import annotations

import asyncio
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from earthforge.core.errors import ConfigError

logger = logging.getLogger(__name__)

#: Supported storage backend identifiers.
VALID_BACKENDS = frozenset({"s3", "gcs", "azure", "local"})

#: Default STAC API endpoint used when none is configured.
DEFAULT_STAC_API = "https://earth-search.aws.element84.com/v1"

_DEFAULT_CONFIG = """\
# EarthForge configuration
# Documentation: https://earthforge-geo.github.io/earthforge/config

[profiles.default]
stac_api = "https://earth-search.aws.element84.com/v1"
storage = "local"

[profiles.default.storage_options]
root = "."
"""


@dataclass(frozen=True, slots=True)
class EarthForgeProfile:
    """A named configuration profile.

    Parameters:
        name: Profile identifier (e.g. ``"default"``, ``"planetary"``).
        stac_api: Base URL for the STAC API, or ``None`` if not configured.
        storage_backend: One of ``"s3"``, ``"gcs"``, ``"azure"``, ``"local"``.
        storage_options: Backend-specific key/value pairs (region, credentials, etc.).

    Raises:
        ConfigError: If ``storage_backend`` is not in ``VALID_BACKENDS``.
    """

    name: str
    stac_api: str | None = None
    storage_backend: str = "local"
    storage_options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.storage_backend not in VALID_BACKENDS:
            msg = (
                f"Unknown storage backend {self.storage_backend!r} in profile "
                f"{self.name!r}. Valid options: {', '.join(sorted(VALID_BACKENDS))}"
            )
            raise ConfigError(msg)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, object]) -> Self:
        """Construct a profile from a parsed TOML dictionary.

        Parameters:
            name: The profile name key.
            data: The TOML table for this profile.

        Returns:
            A validated ``EarthForgeProfile``.

        Raises:
            ConfigError: If required fields are missing or have wrong types.
        """
        stac_api = data.get("stac_api")
        if stac_api is not None and not isinstance(stac_api, str):
            raise ConfigError(f"Profile {name!r}: stac_api must be a string")

        storage = data.get("storage", "local")
        if not isinstance(storage, str):
            raise ConfigError(f"Profile {name!r}: storage must be a string")

        raw_options = data.get("storage_options", {})
        if not isinstance(raw_options, dict):
            raise ConfigError(f"Profile {name!r}: storage_options must be a table")

        storage_options: dict[str, str] = {}
        for k, v in raw_options.items():
            if not isinstance(v, str):
                raise ConfigError(
                    f"Profile {name!r}: storage_options.{k} must be a string, "
                    f"got {type(v).__name__}"
                )
            storage_options[k] = v

        return cls(
            name=name,
            stac_api=stac_api if isinstance(stac_api, str) else None,
            storage_backend=storage,
            storage_options=storage_options,
        )


def config_dir() -> Path:
    """Return the EarthForge configuration directory.

    Returns:
        ``Path("~/.earthforge")`` expanded to an absolute path.
    """
    return Path.home() / ".earthforge"


def _config_file() -> Path:
    """Return the path to the main config file."""
    return config_dir() / "config.toml"


async def load_profile(name: str = "default") -> EarthForgeProfile:
    """Load a named profile from the configuration file.

    If no config file exists, returns a built-in default profile (for the
    ``"default"`` name) or raises ``ConfigError`` for any other name.

    Parameters:
        name: Profile name to load.

    Returns:
        The resolved ``EarthForgeProfile``.

    Raises:
        ConfigError: If the config file is malformed, the profile doesn't exist,
                     or field validation fails.
    """
    path = _config_file()

    if not path.exists():
        logger.debug("No config file at %s, using built-in defaults", path)
        if name == "default":
            return EarthForgeProfile(
                name="default",
                stac_api=DEFAULT_STAC_API,
                storage_backend="local",
                storage_options={"root": "."},
            )
        raise ConfigError(
            f"Profile {name!r} not found: no config file at {path}. "
            f"Run 'earthforge config init' to create one."
        )

    try:
        raw = path.read_bytes()
        config = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        raise ConfigError(f"Config file {path} is missing [profiles] section")

    if name not in profiles:
        available = ", ".join(sorted(profiles.keys())) or "(none)"
        raise ConfigError(f"Profile {name!r} not found in {path}. Available: {available}")

    profile_data = profiles[name]
    if not isinstance(profile_data, dict):
        raise ConfigError(f"Profile {name!r} must be a TOML table")

    return EarthForgeProfile.from_dict(name, profile_data)


def load_profile_sync(name: str = "default") -> EarthForgeProfile:
    """Synchronous convenience wrapper for :func:`load_profile`.

    Parameters:
        name: Profile name to load.

    Returns:
        The resolved ``EarthForgeProfile``.

    Raises:
        ConfigError: Same conditions as :func:`load_profile`.
    """
    return asyncio.run(load_profile(name))


async def init_config(*, overwrite: bool = False) -> Path:
    """Create the default configuration file.

    Parameters:
        overwrite: If ``True``, replace an existing config file. If ``False``
                   and the file already exists, raise ``ConfigError``.

    Returns:
        The path to the created config file.

    Raises:
        ConfigError: If the file exists and ``overwrite`` is ``False``,
                     or if the directory cannot be created.
    """
    path = _config_file()

    if path.exists() and not overwrite:
        raise ConfigError(
            f"Config file already exists at {path}. Use overwrite=True to replace it."
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot create config file at {path}: {exc}") from exc

    logger.info("Created config file at %s", path)
    return path
