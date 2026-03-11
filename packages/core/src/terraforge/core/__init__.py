"""TerraForge core — shared types, configuration, storage, output, and format detection.

This package provides the foundational layer that all TerraForge domain packages
depend on. It wraps third-party libraries (httpx, obstore, rich) behind stable
interfaces so domain code never imports them directly.
"""

__version__ = "0.1.0"
