"""IES Lighting Library retrieval (BM25 over the ingested chunks).

Loads the per-page prose corpus produced by `scripts/ingest_ies_library.py`
(`knowledge/chunks.jsonl`) and exposes a `retrieve(query, k)` function used
by LLM-2 to inject relevant IES guidance into the design intent prompt.

Why BM25 instead of vector embeddings (for v1):
- Zero extra API key / cost (no OpenAI / Voyage dependency).
- Fast enough at 3933 chunks: index loads in <500ms, queries return in <50ms.
- Lighting design queries carry strong domain terms ("bedroom", "elderly",
  "cove", "fluted", "headboard") which BM25 lexical matching handles well.
- The corpus + retrieval interface is the integration point. Swapping in
  semantic embeddings later is one module change; the LLM-2 wire-up stays.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rank_bm25 import BM25Okapi


@dataclass(frozen=True)
class Chunk:
    """One retrievable record from the IES library corpus."""
    doc_id: str
    title: str
    series: str        # RP, LP, LM, TM, ...
    page: int
    n_pages: int
    text: str


_KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"
_CHUNKS_FILE = _KNOWLEDGE_DIR / "chunks.jsonl"

# Residential whitelist (founder rule: we only design residential lighting).
# Split into two buckets:
#   1. Residential-specific docs (always include)
#   2. Horizontal docs that apply universally — design principles, daylight,
#      controls, vision science, LED sources, circadian. These are NOT
#      domain-specific to commercial; they apply to residential too.
# Everything else (offices, retail, healthcare, roadway, industrial,
# museums, theaters, sports, airports, etc.) is excluded so noise from
# other verticals doesn't surface in residential queries.
_RESIDENTIAL_DOC_IDS: frozenset[str] = frozenset({
    # Residential-specific
    "RP-11-20",   # Residential Environments
    "RP-28-20",   # Lighting for Older Adults and Visually Impaired
    # Universal — design principles applicable to residential
    "LP-1-20",    # Designing Quality Lighting for People
    "LP-3-20",    # Daylighting (windows / French windows)
    "LP-4-20",    # Light Sources (LED / CCT / CRI)
    "LP-6-20",    # Lighting Controls (dimming, scenes)
    "LP-16-22",   # Control Intent Narratives (scene programming)
    "LS-2-20",    # Concepts and Language of Lighting (terminology)
    "LS-8-20",    # Vision — Perceptions and Performance
    "TM-18-18",   # Visual, Circadian, Neuroendocrine effects
    "TM-24-20",   # Recommended Illuminance Adjustment (older adults uplift)
    "RP-42-20",   # Dimming and Control Method Designations
    "RP-46-23",   # Physiological and Behavioral Effects of light
})

# Single regex strips light HTML / markdown noise and runs of whitespace.
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase + alphanumeric-only word tokens for BM25."""
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if t]


def _load_chunks() -> list[Chunk]:
    """Read every line of chunks.jsonl into a Chunk, filtered to residential.

    Non-residential vertical docs (commercial offices, retail, healthcare,
    roadway, industrial, museums, theaters, sports, etc.) are skipped at
    load time so they never compete for the BM25 top-K. See
    `_RESIDENTIAL_DOC_IDS` for the active whitelist.
    """
    if not _CHUNKS_FILE.exists():
        return []
    out: list[Chunk] = []
    for line in _CHUNKS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        doc_id = data.get("doc_id", "?")
        if doc_id not in _RESIDENTIAL_DOC_IDS:
            continue
        out.append(Chunk(
            doc_id=doc_id,
            title=data.get("title", "?"),
            series=data.get("series", "?"),
            page=int(data.get("page", 0)),
            n_pages=int(data.get("n_pages", 0)),
            text=data.get("text", ""),
        ))
    return out


@cache
def _bm25_index() -> tuple[BM25Okapi, list[Chunk]]:
    """Build the BM25 index once and memoize for the process lifetime.

    Returns ``(index, chunks)`` so the retrieve fn can look up the chunk
    that corresponds to each BM25-scored document position.
    """
    chunks = _load_chunks()
    if not chunks:
        # Empty corpus — return a trivial index that scores everything 0
        return BM25Okapi([["__empty__"]]), []
    tokenized = [_tokenize(c.text) for c in chunks]
    return BM25Okapi(tokenized), chunks


def retrieve(query: str, *, k: int = 8) -> list[Chunk]:
    """Return the top-K IES corpus chunks for the query, by BM25 score.

    Returns an empty list when the corpus isn't available (knowledge/ not
    populated). Caller should handle empty-list gracefully — no retrieval
    is better than a crash when the index is missing.
    """
    index, chunks = _bm25_index()
    if not chunks:
        return []
    scores = index.get_scores(_tokenize(query))
    # argsort descending, take top-K
    ranked = sorted(
        enumerate(scores), key=lambda pair: pair[1], reverse=True,
    )
    top = []
    for idx, score in ranked[:k]:
        if score <= 0:
            break
        top.append(chunks[idx])
    return top


def format_chunks_for_prompt(chunks: list[Chunk], *, max_chars: int = 6000) -> str:
    """Render retrieved chunks as Markdown for injection into the LLM prompt.

    Truncates each chunk to keep the total under `max_chars` so we don't
    blow up the prompt size on long-page chunks.
    """
    if not chunks:
        return ""
    parts: list[str] = []
    budget = max_chars
    per_chunk = max(400, max_chars // max(len(chunks), 1))
    for c in chunks:
        if budget <= 0:
            break
        text = c.text.strip()
        if len(text) > per_chunk:
            text = text[:per_chunk].rstrip() + " …"
        snippet = (
            f"### [{c.doc_id}, page {c.page}] {c.title}\n\n{text}\n"
        )
        if len(snippet) > budget:
            break
        parts.append(snippet)
        budget -= len(snippet)
    return "\n".join(parts)
