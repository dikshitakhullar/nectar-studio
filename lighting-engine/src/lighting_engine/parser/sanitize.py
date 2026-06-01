"""DXF re-sync sanitizer.

DXF (ASCII) is strictly alternating: each (group-code line, value line) pair
represents one tag. Some converters (LibreDWG) spill long MText values across
several physical lines without continuation, desyncing the stream. We walk the
file expecting code/value alternation; when we expect a code but the line is
not an integer, we merge it into the previous value line as a spilled
continuation.
"""

from pathlib import Path


def _is_int(s: str) -> bool:
    try:
        int(s.strip())
        return True
    except ValueError:
        return False


def sanitize_dxf_lines(lines: list[str]) -> tuple[list[str], int]:
    """Re-sync a list of DXF lines. Returns (sanitized_lines, num_merges)."""
    out: list[str] = []
    expect_code = True
    merges = 0
    for line in lines:
        if expect_code:
            if _is_int(line):
                out.append(line)
                expect_code = False
            else:
                # spilled continuation — merge into previous value line
                if out:
                    out[-1] = out[-1] + line
                    merges += 1
                else:
                    out.append(line)
        else:
            out.append(line)
            expect_code = True
    return out, merges


def sanitize_dxf_file(src: Path, dst: Path) -> int:
    """Sanitize the DXF at `src` and write to `dst`. Returns merge count."""
    with src.open("r", encoding="utf-8", errors="replace", newline="") as f:
        raw = f.read().splitlines()
    sanitized, merges = sanitize_dxf_lines(raw)
    with dst.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(sanitized))
    return merges
