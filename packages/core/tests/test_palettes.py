"""Tests for the EarthForge colorblind-safe palette module."""

from __future__ import annotations

import re

from earthforge.core.palettes import (
    CATEGORICAL,
    CIVIDIS,
    DIVERGING,
    DIVERGING_BRBG,
    PAIRED,
    SEQUENTIAL,
    SET2,
    VIRIDIS,
)

_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


class TestPaletteFormat:
    """All palette entries must be valid lowercase 6-digit hex colors."""

    def test_viridis_hex(self) -> None:
        for color in VIRIDIS:
            assert _HEX_RE.match(color), f"Invalid hex: {color}"

    def test_cividis_hex(self) -> None:
        for color in CIVIDIS:
            assert _HEX_RE.match(color), f"Invalid hex: {color}"

    def test_diverging_hex(self) -> None:
        for color in DIVERGING_BRBG:
            assert _HEX_RE.match(color), f"Invalid hex: {color}"

    def test_set2_hex(self) -> None:
        for color in SET2:
            assert _HEX_RE.match(color), f"Invalid hex: {color}"

    def test_paired_hex(self) -> None:
        for color in PAIRED:
            assert _HEX_RE.match(color), f"Invalid hex: {color}"


class TestPaletteLengths:
    """Palettes must have expected stop counts."""

    def test_viridis_length(self) -> None:
        assert len(VIRIDIS) == 9

    def test_cividis_length(self) -> None:
        assert len(CIVIDIS) == 9

    def test_diverging_length(self) -> None:
        assert len(DIVERGING_BRBG) == 9

    def test_diverging_midpoint_is_neutral(self) -> None:
        assert DIVERGING_BRBG[4] == "#f5f5f5"

    def test_set2_length(self) -> None:
        assert len(SET2) == 8

    def test_paired_length(self) -> None:
        assert len(PAIRED) == 12


class TestConvenienceGroupings:
    """Convenience dicts must reference the correct palette lists."""

    def test_sequential_keys(self) -> None:
        assert set(SEQUENTIAL.keys()) == {"viridis", "cividis"}

    def test_diverging_keys(self) -> None:
        assert set(DIVERGING.keys()) == {"brbg"}

    def test_categorical_keys(self) -> None:
        assert set(CATEGORICAL.keys()) == {"set2", "paired"}

    def test_sequential_viridis_identity(self) -> None:
        assert SEQUENTIAL["viridis"] is VIRIDIS

    def test_categorical_paired_identity(self) -> None:
        assert CATEGORICAL["paired"] is PAIRED
