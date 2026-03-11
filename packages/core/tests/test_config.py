"""Tests for EarthForge configuration management."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthforge.core.config import (
    EarthForgeProfile,
    init_config,
    load_profile,
)
from earthforge.core.errors import ConfigError

# ---------------------------------------------------------------------------
# EarthForgeProfile
# ---------------------------------------------------------------------------


class TestEarthForgeProfile:
    """Tests for the EarthForgeProfile dataclass."""

    def test_defaults(self) -> None:
        p = EarthForgeProfile(name="test")
        assert p.name == "test"
        assert p.stac_api is None
        assert p.storage_backend == "local"
        assert p.storage_options == {}

    def test_valid_backends(self) -> None:
        for backend in ("s3", "gcs", "azure", "local"):
            p = EarthForgeProfile(name="x", storage_backend=backend)
            assert p.storage_backend == backend

    def test_invalid_backend_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown storage backend"):
            EarthForgeProfile(name="bad", storage_backend="hdfs")

    def test_frozen(self) -> None:
        p = EarthForgeProfile(name="x")
        with pytest.raises(AttributeError):
            p.name = "y"  # type: ignore[misc]

    def test_from_dict_minimal(self) -> None:
        p = EarthForgeProfile.from_dict("test", {})
        assert p.name == "test"
        assert p.storage_backend == "local"

    def test_from_dict_full(self) -> None:
        data: dict[str, object] = {
            "stac_api": "https://example.com/stac",
            "storage": "s3",
            "storage_options": {
                "region": "us-west-2",
                "endpoint": "https://s3.example.com",
            },
        }
        p = EarthForgeProfile.from_dict("prod", data)
        assert p.stac_api == "https://example.com/stac"
        assert p.storage_backend == "s3"
        assert p.storage_options["region"] == "us-west-2"

    def test_from_dict_bad_stac_api_type(self) -> None:
        with pytest.raises(ConfigError, match="stac_api must be a string"):
            EarthForgeProfile.from_dict("x", {"stac_api": 123})

    def test_from_dict_bad_storage_type(self) -> None:
        with pytest.raises(ConfigError, match="storage must be a string"):
            EarthForgeProfile.from_dict("x", {"storage": 42})

    def test_from_dict_bad_storage_options_type(self) -> None:
        with pytest.raises(ConfigError, match="storage_options must be a table"):
            EarthForgeProfile.from_dict("x", {"storage_options": "nope"})

    def test_from_dict_bad_storage_option_value(self) -> None:
        with pytest.raises(ConfigError, match="must be a string"):
            EarthForgeProfile.from_dict("x", {"storage_options": {"port": 443}})


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------

MP = pytest.MonkeyPatch


class TestLoadProfile:
    """Tests for async profile loading."""

    async def test_default_without_config_file(self, tmp_path: Path, monkeypatch: MP) -> None:
        """No config file => built-in defaults for 'default' profile."""
        fake = tmp_path / "nonexistent.toml"
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: fake)
        profile = await load_profile("default")
        assert profile.name == "default"
        assert profile.stac_api is not None
        assert profile.storage_backend == "local"

    async def test_missing_profile_without_config_file(
        self, tmp_path: Path, monkeypatch: MP
    ) -> None:
        """Non-default profile with no config file raises."""
        fake = tmp_path / "nonexistent.toml"
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: fake)
        with pytest.raises(ConfigError, match="not found"):
            await load_profile("planetary")

    async def test_load_from_toml(self, tmp_path: Path, monkeypatch: MP) -> None:
        """Load a profile from an actual TOML config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[profiles.myprofile]\n"
            'stac_api = "https://stac.example.com"\n'
            'storage = "gcs"\n'
            "\n"
            "[profiles.myprofile.storage_options]\n"
            'project = "my-gcp-project"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: config_file)
        profile = await load_profile("myprofile")
        assert profile.name == "myprofile"
        assert profile.stac_api == "https://stac.example.com"
        assert profile.storage_backend == "gcs"
        assert profile.storage_options["project"] == "my-gcp-project"

    async def test_missing_profile_in_file(self, tmp_path: Path, monkeypatch: MP) -> None:
        """Missing profile in file raises with available list."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[profiles.alpha]\nstorage = "local"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: config_file)
        with pytest.raises(ConfigError, match="Available: alpha"):
            await load_profile("beta")

    async def test_invalid_toml(self, tmp_path: Path, monkeypatch: MP) -> None:
        """Malformed TOML raises a ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("not valid toml [[[", encoding="utf-8")
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: config_file)
        with pytest.raises(ConfigError, match="Invalid TOML"):
            await load_profile()

    async def test_missing_profiles_section(self, tmp_path: Path, monkeypatch: MP) -> None:
        """Config file without [profiles] section raises."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('title = "oops"\n', encoding="utf-8")
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: config_file)
        with pytest.raises(ConfigError, match=r"missing.*profiles"):
            await load_profile()


# ---------------------------------------------------------------------------
# init_config
# ---------------------------------------------------------------------------


class TestInitConfig:
    """Tests for config file creation."""

    async def test_creates_file(self, tmp_path: Path, monkeypatch: MP) -> None:
        target = tmp_path / ".earthforge" / "config.toml"
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: target)
        result = await init_config()
        assert result == target
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "[profiles.default]" in content

    async def test_refuses_overwrite_by_default(self, tmp_path: Path, monkeypatch: MP) -> None:
        target = tmp_path / "config.toml"
        target.write_text("existing", encoding="utf-8")
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: target)
        with pytest.raises(ConfigError, match="already exists"):
            await init_config()

    async def test_overwrite_when_requested(self, tmp_path: Path, monkeypatch: MP) -> None:
        target = tmp_path / "config.toml"
        target.write_text("old content", encoding="utf-8")
        monkeypatch.setattr("earthforge.core.config._config_file", lambda: target)
        await init_config(overwrite=True)
        assert "[profiles.default]" in target.read_text(encoding="utf-8")
