"""Pytest configuration for earthforge-pipeline tests."""

import sys
from pathlib import Path

pkg_root = Path(__file__).parent.parent
repo_root = pkg_root.parent.parent

sys.path.insert(0, str(pkg_root / "src"))
sys.path.insert(0, str(repo_root / "packages" / "core" / "src"))
sys.path.insert(0, str(repo_root / "packages" / "stac" / "src"))
sys.path.insert(0, str(repo_root / "packages" / "raster" / "src"))
sys.path.insert(0, str(repo_root / "packages" / "vector" / "src"))
