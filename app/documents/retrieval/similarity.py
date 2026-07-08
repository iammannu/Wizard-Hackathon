"""
Shared cosine-similarity helper for single vector pairs. Used by mmr.py's
redundancy term and, as of Milestone 2, by the Evidence Engine's scorer,
deduplication, and conflict detection — all four need the same "how similar
are these two individual vectors" primitive. SQLiteVectorStore's bulk scan
is a different shape (one query vector against many candidates at once) and
stays its own numpy-vectorized implementation rather than looping this
per-pair function.
"""
import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    a_arr, b_arr = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)) or 1.0
    return float(np.dot(a_arr, b_arr) / denom)
