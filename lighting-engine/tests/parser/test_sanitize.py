from lighting_engine.parser.sanitize import sanitize_dxf_lines


def test_well_formed_dxf_unchanged():
    lines = ["0", "SECTION", "2", "HEADER", "0", "ENDSEC", "0", "EOF"]
    out, merges = sanitize_dxf_lines(lines)
    assert out == lines
    assert merges == 0


def test_spilled_value_lines_are_merged_into_previous_value():
    # Group code 1 expects a single value line, but here the value spilled across 3 lines
    lines = [
        "0", "MTEXT",
        "1", "first part of long text",
        "  AND CONTINUES HERE",
        "  AND MORE HERE",
        "70", "0",
    ]
    out, merges = sanitize_dxf_lines(lines)
    assert merges == 2
    assert out == [
        "0", "MTEXT",
        "1", "first part of long text  AND CONTINUES HERE  AND MORE HERE",
        "70", "0",
    ]


def test_negative_integer_group_codes_accepted():
    # group codes can be negative in some sections
    lines = ["-1", "value", "0", "EOF"]
    out, _ = sanitize_dxf_lines(lines)
    assert out == lines


def test_value_line_can_be_anything_including_text_that_looks_like_a_number():
    # A value like " 12 " is fine after a code; we should not treat it as a misplaced code
    lines = ["1", " 12 ", "0", "EOF"]
    out, merges = sanitize_dxf_lines(lines)
    assert merges == 0
    assert out == lines
