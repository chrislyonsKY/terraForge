"""Pytest configuration for earthforge-cube tests.

Adds the cube and core src directories to sys.path so tests can import
earthforge.cube and earthforge.core without an editable install.
"""

import sys
from pathlib import Path

# Resolve paths relative to this conftest's parent (packages/cube/)
pkg_root = Path(__file__).parent.parent
repo_root = pkg_root.parent.parent

sys.path.insert(0, str(pkg_root / "src"))
sys.path.insert(0, str(repo_root / "packages" / "core" / "src"))
