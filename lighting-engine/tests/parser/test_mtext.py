from lighting_engine.parser.mtext import parse_room_label, strip_mtext_codes


def test_strip_basic_alignment_and_paragraph_codes():
    raw = r"\A1;\pxqc;MASTER BEDROOM"
    assert strip_mtext_codes(raw) == "MASTER BEDROOM"


def test_strip_stacked_fraction():
    raw = r"\A1;\pxqc;MASTER TOILET | 13'-0\" x 12'-4{\H0.7x;\S1#2;}\""
    cleaned = strip_mtext_codes(raw)
    assert "MASTER TOILET" in cleaned
    # stacked fraction \S1#2; should be removed (we don't need the ½)
    assert "\\S" not in cleaned


def test_strip_font_directive():
    raw = r"\fArial|b1|i0|c0|p34;\LFIRST FLOOR - FURNITURE PLAN"
    cleaned = strip_mtext_codes(raw)
    assert "FIRST FLOOR - FURNITURE PLAN" in cleaned


def test_parse_label_with_feet_inches_dims():
    name, w_in, h_in = parse_room_label(r"\A1;\pxqc;BEDROOM - 1 | 16'-9\" x 16'-9\"")
    assert name == "BEDROOM - 1"
    assert w_in == 16 * 12 + 9
    assert h_in == 16 * 12 + 9


def test_parse_label_with_x_uppercase_and_no_inches():
    name, w_in, h_in = parse_room_label(r"\pxqc;STUDY ROOM | 22'-0\"X16'-9\"")
    assert name == "STUDY ROOM"
    assert w_in == 22 * 12
    assert h_in == 16 * 12 + 9


def test_parse_label_with_no_dims_returns_none():
    name, w, h = parse_room_label(r"\A1;\pxqc;UP")
    assert name == "UP"
    assert w is None and h is None


def test_parse_label_strips_pipe_separator():
    name, w, h = parse_room_label(r"\A1;\pxqc;DRESS - 1 | 9'-3\" x 11'-9\"")
    assert name == "DRESS - 1"
