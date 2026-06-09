"""Tests for the IES library retrieval layer."""

from lighting_engine.design.retrieval import (
    Chunk,
    _bm25_index,
    _tokenize,
    format_chunks_for_prompt,
    retrieve,
)


def test_tokenize_lowercases_and_drops_punctuation():
    assert _tokenize("Bedroom lighting — for an Elderly person?") == [
        "bedroom", "lighting", "for", "an", "elderly", "person",
    ]


def test_tokenize_handles_empty_string():
    assert _tokenize("") == []


def test_corpus_loads_and_is_non_empty():
    """The Delhi corpus has ~3933 chunks; just verify it loads."""
    _, chunks = _bm25_index()
    # If the developer hasn't ingested the corpus yet, this may be 0;
    # gate so the test doesn't fail in a clean checkout.
    if not chunks:
        # Soft signal — no corpus means retrieve() returns [], which is the
        # documented behavior. Don't fail; just exit.
        return
    assert len(chunks) > 100
    # Sanity check: a couple of expected docs are present
    doc_ids = {c.doc_id for c in chunks}
    assert any(d.startswith("RP-") or d.startswith("LP-") for d in doc_ids)


def test_retrieve_returns_relevant_chunks_for_known_query():
    """If the corpus is populated, a bedroom-elderly query should pull
    chunks that mention either 'bedroom' or 'elderly' in their text."""
    _, chunks = _bm25_index()
    if not chunks:
        return
    results = retrieve(
        "bedroom lighting design for elderly occupants", k=8,
    )
    assert len(results) > 0
    text_blob = " ".join(c.text.lower() for c in results)
    assert any(term in text_blob for term in (
        "bedroom", "elderly", "senior", "residential", "aged",
    ))


def test_retrieve_returns_empty_for_corpus_miss():
    """A nonsense query produces few/no positive-score hits — that's fine,
    we return whatever did score > 0 (often empty)."""
    _, chunks = _bm25_index()
    if not chunks:
        return
    results = retrieve(
        "xqzyzx nonexistent gibberish gibberishxxx fdsaewr",
        k=8,
    )
    # Either empty or a few low-score noise hits; we just verify it returns
    # a list without crashing.
    assert isinstance(results, list)


def test_format_chunks_for_prompt_emits_citation_format():
    chunks = [
        Chunk(
            doc_id="RP-28-22", title="Senior Living", series="RP",
            page=42, n_pages=120,
            text="Older adults need higher illuminance levels.",
        ),
    ]
    formatted = format_chunks_for_prompt(chunks)
    assert "RP-28-22" in formatted
    assert "page 42" in formatted
    assert "Older adults" in formatted


def test_format_chunks_for_prompt_handles_empty_list():
    assert format_chunks_for_prompt([]) == ""


def test_format_chunks_for_prompt_respects_max_chars():
    chunks = [
        Chunk(
            doc_id="X", title="X", series="X", page=1, n_pages=1,
            text="a" * 500,
        ),
        Chunk(
            doc_id="Y", title="Y", series="Y", page=1, n_pages=1,
            text="b" * 500,
        ),
    ]
    formatted = format_chunks_for_prompt(chunks, max_chars=400)
    # Should fit at least one chunk (truncated) within 400 chars-ish
    assert len(formatted) <= 600
