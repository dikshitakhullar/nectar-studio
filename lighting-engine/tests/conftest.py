"""Root tests conftest: ensure the project root is on sys.path so tests can
import ``scripts.*`` alongside the installed ``lighting_engine`` package.

The ``tests/`` directory is prepended to sys.path by pytest (because
``tests/__init__.py`` exists), which means ``tests/scripts/`` would shadow the
top-level ``scripts/`` package.  We fix this by eagerly importing
``scripts.visualize_parse`` from the project root via importlib so the correct
module is seeded into sys.modules before pytest's collection machinery runs.
"""

import importlib.util
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load .env.local (preferred — monorepo Next.js convention) or fall back to
# .env. Walks up from cwd so it finds the file at the nectar-studio root even
# when pytest is invoked from the lighting-engine subdirectory. Done at
# import time so `pytest.mark.skipif(not os.environ.get(...))` decorators
# evaluated during collection see the variables.
load_dotenv(find_dotenv(".env.local", usecwd=True) or find_dotenv(usecwd=True))

_root = Path(__file__).parent.parent
_scripts_init = _root / "scripts" / "__init__.py"
_scripts_vp = _root / "scripts" / "visualize_parse.py"

# Register the top-level scripts package from the project root so that
# `from scripts.visualize_parse import ...` resolves to the right file even
# when tests/ is earlier on sys.path.
if "scripts" not in sys.modules:
    spec = importlib.util.spec_from_file_location("scripts", str(_scripts_init))
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["scripts"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

if "scripts.visualize_parse" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "scripts.visualize_parse", str(_scripts_vp)
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["scripts.visualize_parse"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
