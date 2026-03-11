"""Tests for the TerraForge error hierarchy."""

from __future__ import annotations

import pytest

from terraforge.core.errors import (
    ConfigError,
    FormatDetectionError,
    HttpError,
    StorageError,
    TerraForgeError,
)


class TestTerraForgeError:
    """Tests for the base TerraForgeError."""

    def test_message_stored(self) -> None:
        err = TerraForgeError("something broke")
        assert str(err) == "something broke"

    def test_default_exit_code(self) -> None:
        err = TerraForgeError("oops")
        assert err.exit_code == 1

    def test_custom_exit_code(self) -> None:
        err = TerraForgeError("oops", exit_code=42)
        assert err.exit_code == 42

    def test_is_exception(self) -> None:
        with pytest.raises(TerraForgeError):
            raise TerraForgeError("test")


class TestConfigError:
    """Tests for ConfigError."""

    def test_inherits_from_base(self) -> None:
        err = ConfigError("bad profile")
        assert isinstance(err, TerraForgeError)

    def test_exit_code(self) -> None:
        err = ConfigError("bad profile")
        assert err.exit_code == 2

    def test_caught_by_base(self) -> None:
        with pytest.raises(TerraForgeError):
            raise ConfigError("missing config")


class TestStorageError:
    """Tests for StorageError."""

    def test_exit_code(self) -> None:
        err = StorageError("access denied")
        assert err.exit_code == 3

    def test_inherits_from_base(self) -> None:
        assert isinstance(StorageError("x"), TerraForgeError)


class TestHttpError:
    """Tests for HttpError."""

    def test_exit_code(self) -> None:
        err = HttpError("timeout")
        assert err.exit_code == 4

    def test_status_code_stored(self) -> None:
        err = HttpError("not found", status_code=404)
        assert err.status_code == 404

    def test_status_code_defaults_to_none(self) -> None:
        err = HttpError("connection refused")
        assert err.status_code is None

    def test_inherits_from_base(self) -> None:
        assert isinstance(HttpError("x"), TerraForgeError)


class TestFormatDetectionError:
    """Tests for FormatDetectionError."""

    def test_exit_code(self) -> None:
        err = FormatDetectionError("unknown format")
        assert err.exit_code == 5

    def test_inherits_from_base(self) -> None:
        assert isinstance(FormatDetectionError("x"), TerraForgeError)
