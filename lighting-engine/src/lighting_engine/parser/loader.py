"""Robust DWG/DXF loader.

- `.dwg`: shell out to LibreDWG `dwg2dxf` to produce a `.dxf`.
- `.dxf`: skip conversion.
- Always: run the sanitizer (handles LibreDWG's spilled-value-line bug).
- Always: open via `ezdxf.recover.readfile` (forgives minor structural issues).
- Always: validate `$INSUNITS` against the supported unit (v1 = inches).
"""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ezdxf import recover
from ezdxf.document import Drawing
from ezdxf.filemanagement import (
    readfile as ezdxf_readfile,  # type: ignore[reportUnknownVariableType]
)
from ezdxf.lldxf.const import DXFStructureError

from lighting_engine.parser.sanitize import sanitize_dxf_file

SourceFormat = Literal["dwg", "dxf"]


@dataclass
class LoadReport:
    document: Drawing
    source_format: SourceFormat
    merges: int  # how many spilled lines the sanitizer fixed
    auditor_errors: int  # ezdxf recover errors remaining
    auditor_fixes: int  # ezdxf recover fixes applied
    insunits: int  # DXF $INSUNITS header (1=in, 4=mm, 6=m, 2=ft, 0=unitless)


# Code → human label for error messages
_INSUNITS_LABELS = {
    0: "unitless",
    1: "inches",
    2: "feet",
    4: "millimetres",
    5: "centimetres",
    6: "metres",
}


def _check_units(doc: Drawing, strict: bool) -> int:
    """Read $INSUNITS; raise in strict mode if not 1 (inches), the v1 supported unit."""
    insunits = int(doc.header.get("$INSUNITS", 0))
    if strict and insunits != 1:
        label = _INSUNITS_LABELS.get(insunits, f"code {insunits}")
        raise ValueError(
            f"DXF $INSUNITS = {insunits} ({label}); v1 supports only INSUNITS=1 (inches). "
            "Re-export the file in inches, or pass strict_units=False to override."
        )
    return insunits


def _dwg_to_dxf(dwg_path: Path, dxf_path: Path) -> None:
    if shutil.which("dwg2dxf") is None:
        raise RuntimeError(
            "dwg2dxf not found on PATH — install LibreDWG (`brew install libredwg`)"
        )
    result = subprocess.run(
        ["dwg2dxf", "-o", str(dxf_path), str(dwg_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not dxf_path.exists():
        raise RuntimeError(
            f"dwg2dxf failed (rc={result.returncode}): {result.stderr.strip()[:500]}"
        )


def load_drawing(path: Path | str, *, strict_units: bool = True) -> LoadReport:
    """Load a `.dwg` or `.dxf` into an ezdxf Document, sanitizing as needed.

    Raises `ValueError` if the file uses INSUNITS != 1 (inches) and `strict_units`
    is True. Pass `strict_units=False` to load anyway (caller handles units).
    """
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)

    ext = src.suffix.lower()
    if ext == ".dwg":
        with tempfile.TemporaryDirectory() as td:
            raw_dxf = Path(td) / "raw.dxf"
            clean_dxf = Path(td) / "clean.dxf"
            _dwg_to_dxf(src, raw_dxf)
            merges = sanitize_dxf_file(raw_dxf, clean_dxf)
            doc, auditor = recover.readfile(str(clean_dxf))
        insunits = _check_units(doc, strict_units)
        return LoadReport(
            document=doc,
            source_format="dwg",
            merges=merges,
            auditor_errors=len(auditor.errors),
            auditor_fixes=len(auditor.fixes),
            insunits=insunits,
        )
    elif ext == ".dxf":
        try:
            doc = ezdxf_readfile(str(src))
            insunits = _check_units(doc, strict_units)
            return LoadReport(
                document=doc,
                source_format="dxf",
                merges=0,
                auditor_errors=0,
                auditor_fixes=0,
                insunits=insunits,
            )
        except DXFStructureError:
            with tempfile.TemporaryDirectory() as td:
                clean_dxf = Path(td) / "clean.dxf"
                merges = sanitize_dxf_file(src, clean_dxf)
                doc, auditor = recover.readfile(str(clean_dxf))
            insunits = _check_units(doc, strict_units)
            return LoadReport(
                document=doc,
                source_format="dxf",
                merges=merges,
                auditor_errors=len(auditor.errors),
                auditor_fixes=len(auditor.fixes),
                insunits=insunits,
            )
    else:
        raise ValueError(f"unsupported file extension: {ext} (expected .dwg or .dxf)")
