from lighting_engine.parser.layers import LayerRole, classify_layers


def test_recognizes_uppercase_and_mixed_case():
    layer_names = ["WALL", "window", "DOOR", "FIXTURES", "FURNITURE", "GLASS", "0", "Defpoints"]
    result = classify_layers(layer_names)
    assert "WALL" in result[LayerRole.wall]
    assert "window" in result[LayerRole.window]
    assert "DOOR" in result[LayerRole.door]
    assert "FIXTURES" in result[LayerRole.fixture]
    assert "FURNITURE" in result[LayerRole.furniture]
    # GLASS = glazed apertures = same bucket as window (balcony doors are glazed)
    assert "GLASS" in result[LayerRole.window]


def test_unrecognized_layers_excluded():
    result = classify_layers(["A3", "REVISION", "WORKING"])
    for _role, names in result.items():
        assert not any(n in ("A3", "REVISION", "WORKING") for n in names)


def test_dim_and_text_layers_classified_as_annotation():
    result = classify_layers(["DIM", "DIMNSIONS", "TEXT", "TEXT 1"])
    annot = result[LayerRole.annotation]
    assert {"DIM", "DIMNSIONS", "TEXT", "TEXT 1"} <= set(annot)


def test_multi_word_lighting_layer_classified():
    result = classify_layers(["wall light", "WALL ELECTRICAL"])
    assert "wall light" in result[LayerRole.fixture]
    # WALL ELECTRICAL is ambiguous; we route it to fixture since it carries lighting INSERTs
    assert "WALL ELECTRICAL" in result[LayerRole.fixture]
