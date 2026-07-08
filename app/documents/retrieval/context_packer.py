"""
Context-window packing — greedily fits ranked retrieval results into a
token budget, reusing the existing tiktoken-based chunker.count_tokens
(no new tokenizer dependency, same counting the chunker itself uses so a
"4000 token budget" means the same thing here as it does at ingestion time).
"""
from typing import Sequence, TypeVar

from app.documents.chunking.chunker import count_tokens

# Any object with a `.text: str` attribute (RetrievedChunk, in practice).
T = TypeVar("T")


def pack_context(chunks: Sequence[T], max_tokens: int = 4000) -> list[T]:
    if not chunks:
        return []

    packed: list[T] = []
    tokens_used = 0
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.text)
        remaining = max_tokens - tokens_used
        if remaining <= 0:
            break
        if chunk_tokens <= remaining:
            packed.append(chunk)
            tokens_used += chunk_tokens
            continue

        # Doesn't fully fit — truncate it in if at least 40% still would,
        # otherwise drop it and stop (later, lower-ranked chunks would fit
        # even less well).
        if remaining >= chunk_tokens * 0.4:
            # Token-accurate truncation would require re-encoding; a
            # proportional character truncation is a cheap, close-enough
            # approximation for a "some context beats none" last chunk.
            keep_fraction = remaining / chunk_tokens
            truncated_text = chunk.text[: int(len(chunk.text) * keep_fraction)]
            chunk.text = truncated_text
            packed.append(chunk)
            tokens_used += count_tokens(truncated_text)
        break

    return packed
