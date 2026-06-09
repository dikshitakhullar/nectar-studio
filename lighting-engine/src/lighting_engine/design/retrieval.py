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

# Single regex strips light HTML / markdown noise and runs of whitespace.
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase + alphanumeric-only word tokens for BM25."""
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if t]


def _load_chunks() -> list[Chunk]:
    """Read every line of chunks.jsonl into a Chunk."""
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
        out.append(Chunk(
            doc_id=data.get("doc_id", "?"),
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
