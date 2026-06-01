"""Root conftest: ensure the project root is on sys.path so tests can import
``scripts.*`` alongside the installed ``lighting_engine`` package."""

import sys
from pathlib import Path

# Add lighting-engine/ root so `from scripts.visualize_parse import ...` works.
_root = str(Path(__file__).parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
