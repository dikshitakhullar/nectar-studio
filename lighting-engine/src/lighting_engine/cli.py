"""Lighting-engine CLI. Run via `uv run python -m lighting_engine`."""

import json
from pathlib import Path
from typing import Annotated

import typer

from lighting_engine.parser.pipeline import parse_file

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("parse")
def parse_cmd(
    file: Annotated[Path, typer.Argument(exists=True, readable=True)],
    project_name: Annotated[str, typer.Option("--project", "-p")] = "Untitled project",
    location: Annotated[str, typer.Option("--location", "-l")] = "delhi",
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Write JSON to this path"),
    ] = None,
) -> None:
    """Parse a DWG/DXF into a Project IR + gaps report."""
    project, report = parse_file(file, project_name=project_name, location=location)

    typer.echo(f"\nParsed: {file}")
    typer.echo(f"Rooms found: {len(project.rooms)}")
    for r in project.rooms:
        typer.echo(
            f"  - {r.name:<28}  type={r.type.value:<10}  area={r.area_sqm:.1f} sqm  "
            f"floor={r.floor_level}"
        )
    typer.echo(f"\nGaps ({len(report.missing)}):")
    for m in report.missing:
        typer.echo(f"  [{m.severity.value:<6}] {m.category}: {m.description}")

    payload = {
        "project": project.model_dump(mode="json"),
        "gaps": report.model_dump(mode="json"),
    }
    if out:
        out.write_text(json.dumps(payload, indent=2))
        typer.echo(f"\nWrote: {out}")
    else:
        typer.echo("\n--- JSON (use --out to write to file) ---")
        typer.echo(json.dumps(payload, indent=2)[:1500] + " ...")


if __name__ == "__main__":
    app()
