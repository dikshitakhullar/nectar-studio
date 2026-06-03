"""Export the FastAPI OpenAPI schema to ``shared/openapi.yaml``.

Run as part of CI after the API changes so the studio's TypeScript client
stays in sync with the engine's contract.

Usage::

    uv run python scripts/export_openapi.py [--out PATH]
"""

import argparse
import sys
from pathlib import Path

import yaml

from lighting_engine.api.app import app


def _default_out_path() -> Path:
    """``<repo-root>/shared/openapi.yaml`` — sibling of ``lighting-engine``."""
    here = Path(__file__).resolve()
    # scripts/export_openapi.py → lighting-engine/ → repo root
    repo_root = here.parents[2]
    return repo_root / "shared" / "openapi.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_default_out_path(),
        help="Where to write the YAML schema (default: shared/openapi.yaml)",
    )
    args = parser.parse_args(argv)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    schema = app.openapi()
    yaml_text = yaml.safe_dump(schema, sort_keys=False, default_flow_style=False)
    out_path.write_text(yaml_text)

    print(f"Wrote {out_path} ({len(yaml_text)} bytes, {len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
