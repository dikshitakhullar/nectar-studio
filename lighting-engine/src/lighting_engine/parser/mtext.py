"""MText control-code stripper and room-label dimension parser.

AutoCAD MText embeds inline control codes (\\A, \\pxqc, \\H, \\S, etc.). Real
labels look like `\\A1;\\pxqc;MASTER BEDROOM | 18'-4" x 24'-3"` and we need just
the room name plus the embedded width/height in inches.
"""

import re

# Each pattern strips one family of MText codes. Order matters: font directives
# (which contain `;`) must come before generic `\X...;` patterns.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\\f[^;]*?;"),          # \fArial|b1|i0|c0|p34;
    re.compile(r"\\p[a-zA-Z0-9.,\-+*\s]*?;"),  # \pxqc;, \pi-3,l4,t4;
    re.compile(r"\\H[\d.]+x?;"),         # \H0.7x;
    re.compile(r"\\S[^;]*;"),            # \S1#2;  (stacked fraction)
    re.compile(r"\\A\d+;"),              # \A0; alignment
    re.compile(r"\\C\d+;"),              # \C236; colour
    re.compile(r"\\c\d+;"),              # \c4392845; true colour
    re.compile(r"\\L"),                  # \L underline begin (no semicolon)
    re.compile(r"\\l"),                  # \l underline end
    re.compile(r"\\[OoKkQqWw][\d.\-]*;?"),
    re.compile(r"\\\\"),                 # escaped backslash
]


def strip_mtext_codes(raw: str) -> str:
    """Strip AutoCAD MText control codes from a raw value, returning plain text."""
    text = raw
    for pat in _PATTERNS:
        text = pat.sub("", text)
    text = text.replace("\\P", " ")      # MText newline → space
    text = text.replace("{", "").replace("}", "")
    return text.strip()


_DIM_RE = re.compile(r"(\d+)'\s*-?\s*(\d*)\\?\"?\s*[xX×]\s*(\d+)'?\s*-?\s*(\d*)\\?\"?")


def parse_room_label(raw: str) -> tuple[str, int | None, int | None]:
    """Parse a room label into (name, width_inches, height_inches).

    Returns (name, None, None) if no dimensions found. `name` is uppercase and
    has trailing pipe/space/dash trimmed.
    """
    cleaned = strip_mtext_codes(raw)
    m = _DIM_RE.search(cleaned)
    width_in: int | None = None
    height_in: int | None = None
    name_part = cleaned
    if m:
        ft1, in1, ft2, in2 = m.groups()
        width_in = int(ft1) * 12 + (int(in1) if in1 else 0)
        height_in = int(ft2) * 12 + (int(in2) if in2 else 0)
        name_part = cleaned[: m.start()]
    name = re.sub(r"[|\s\-]+$", "", name_part).strip().upper()
    return name, width_in, height_in
