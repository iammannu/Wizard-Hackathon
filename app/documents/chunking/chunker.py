"""
Section-aware, token-budgeted chunking.

Why token-budgeted, not character-budgeted:
  Embedding models and the retrieval prompt budget both operate in tokens.
  A character count is a proxy that drifts badly on financial text (dense
  with numbers, tickers, and punctuation) — tiktoken gives the real count
  cheaply, and it's the same tokenizer family used elsewhere for
  OpenAI-model prompt budgeting, so this becomes reusable beyond chunking.

Why section-aware:
  Chunking is done independently per section (see parsers/html_sections.py)
  rather than on the flattened whole-document text. This keeps a chunk from
  SEC "Item 1A. Risk Factors" from bleeding into "Item 7. MD&A" — retrieval
  and citations should be able to say *which* section a fact came from, and
  that's only possible if the chunk boundary respects it.

Splitting strategy within a section:
  Paragraphs (blank-line separated) are packed greedily up to
  CHUNK_TOKEN_TARGET, with CHUNK_OVERLAP_TOKENS of trailing context carried
  into the next chunk so a fact split across a chunk boundary isn't lost to
  either side. A single paragraph that alone exceeds the budget is split on
  sentence boundaries; a single sentence that still exceeds it is hard-split
  by token count as a last resort — this only happens on pathological input
  (e.g. a table rendered as one unbroken line of text).
"""
import re
from dataclasses import dataclass

import tiktoken

CHUNK_TOKEN_TARGET = 600
CHUNK_OVERLAP_TOKENS = 80

_ENCODING = tiktoken.get_encoding("cl100k_base")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    section: str | None
    text: str
    token_count: int


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def chunk_sections(sections: dict[str, str]) -> list[Chunk]:
    """sections: {section_key: section_text}, from parsers/html_sections.py."""
    chunks: list[Chunk] = []
    for section_key, text in sections.items():
        section_name = None if section_key in ("_full_text", "_preamble") else section_key
        chunks.extend(_chunk_text(text, section_name))
    return chunks


def _chunk_text(text: str, section: str | None) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    units: list[str] = []
    for paragraph in paragraphs:
        if count_tokens(paragraph) <= CHUNK_TOKEN_TARGET:
            units.append(paragraph)
        else:
            units.extend(_split_long_paragraph(paragraph))

    chunks: list[Chunk] = []
    current_units: list[str] = []
    current_tokens = 0

    def flush() -> str | None:
        if not current_units:
            return None
        text_out = "\n\n".join(current_units)
        chunks.append(Chunk(section=section, text=text_out, token_count=count_tokens(text_out)))
        return text_out

    for unit in units:
        unit_tokens = count_tokens(unit)
        if current_tokens + unit_tokens > CHUNK_TOKEN_TARGET and current_units:
            flushed_text = flush()
            current_units = _overlap_tail(flushed_text) if flushed_text else []
            current_tokens = sum(count_tokens(u) for u in current_units)
        current_units.append(unit)
        current_tokens += unit_tokens
    flush()

    return chunks


def _overlap_tail(flushed_text: str) -> list[str]:
    """
    Carry the trailing ~CHUNK_OVERLAP_TOKENS of the chunk just flushed into
    the next one, as a raw token-boundary slice — not whole units.

    A unit-level overlap (carrying whole paragraphs/sentences) breaks down
    the moment a single unit is itself close to CHUNK_TOKEN_TARGET (which is
    the common case here, since _split_long_paragraph packs sentences right
    up to that budget): "carry at least one unit" then means "carry the
    entire previous chunk," doubling chunk sizes instead of adding a small
    tail of context. Slicing by raw tokens sidesteps that regardless of how
    big the contributing units were.
    """
    tokens = _ENCODING.encode(flushed_text)
    if len(tokens) <= CHUNK_OVERLAP_TOKENS:
        return [flushed_text]
    return [_ENCODING.decode(tokens[-CHUNK_OVERLAP_TOKENS:])]


def _split_long_paragraph(paragraph: str) -> list[str]:
    sentences = _SENTENCE_SPLIT_RE.split(paragraph)
    units: list[str] = []
    buffer = ""
    for sentence in sentences:
        if count_tokens(sentence) > CHUNK_TOKEN_TARGET:
            if buffer:
                units.append(buffer)
                buffer = ""
            units.extend(_hard_split(sentence))
            continue
        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if count_tokens(candidate) > CHUNK_TOKEN_TARGET:
            units.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        units.append(buffer)
    return units


def _hard_split(text: str) -> list[str]:
    """Last resort: split by raw token count with no regard for word/sentence
    boundaries. Only reached for a single sentence longer than the whole
    chunk budget — pathological input, not the common path."""
    tokens = _ENCODING.encode(text)
    return [
        _ENCODING.decode(tokens[i:i + CHUNK_TOKEN_TARGET])
        for i in range(0, len(tokens), CHUNK_TOKEN_TARGET)
    ]
