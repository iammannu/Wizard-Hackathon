"""
EmbeddingProvider — pluggable text -> vector backends.

Three implementations, one interface, selected via
Settings.embedding_provider ("openai" | "voyage" | "local"):

  OpenAIEmbeddingProvider   default, runs today with the existing
                            openai_api_key — no new dependency.
  VoyageEmbeddingProvider   a lean httpx call to Voyage's REST API directly
                            (no voyageai SDK dependency, matches this repo's
                            existing lightweight-provider style). Raises
                            loudly if voyage_api_key is unset — same
                            fail-fast convention as
                            app/documents/providers/sec_edgar.py's
                            sec_edgar_user_agent check, not a silent
                            empty-vector fallback.
  LocalEmbeddingProvider    real sentence-transformers inference, not a
                            mock — but sentence-transformers/torch are
                            deliberately NOT in requirements.txt (multi-GB
                            install). The import is lazy, inside __init__,
                            so the app runs fine without it; selecting
                            "local" without the package installed raises a
                            clear, actionable error instead of a stack trace
                            three layers down.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.core.config import get_settings

settings = get_settings()

_VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"


class EmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dimension: int

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, same order in -> same order out."""

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai"

    # text-embedding-3-small = 1536 dims; keep in sync if the model setting changes.
    _KNOWN_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, model: Optional[str] = None):
        from openai import AsyncOpenAI  # already a core dependency (used by app/agents/base.py)

        self.model_name = model or settings.openai_embedding_model
        self.dimension = self._KNOWN_DIMENSIONS.get(self.model_name, 1536)
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        # OpenAI's embeddings endpoint accepts large batches, but we chunk
        # defensively so one oversized request can't blow past API limits.
        batch_size = max(1, settings.embedding_batch_size)
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await self._client.embeddings.create(model=self.model_name, input=batch)
            vectors.extend([item.embedding for item in resp.data])
        return vectors


class VoyageEmbeddingProvider(EmbeddingProvider):
    provider_name = "voyage"

    _KNOWN_DIMENSIONS = {"voyage-3": 1024, "voyage-3-lite": 512, "voyage-large-2": 1536}

    def __init__(self, model: Optional[str] = None):
        api_key = settings.voyage_api_key.strip()
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is not configured. Set voyage_api_key in .env "
                "before selecting embedding_provider=voyage — sign up at "
                "https://www.voyageai.com/."
            )
        self._api_key = api_key
        self.model_name = model or settings.voyage_embedding_model
        self.dimension = self._KNOWN_DIMENSIONS.get(self.model_name, 1024)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = max(1, settings.embedding_batch_size)
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = await client.post(
                    _VOYAGE_EMBEDDINGS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"input": batch, "model": self.model_name},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                vectors.extend([item["embedding"] for item in data])
        return vectors


class LocalEmbeddingProvider(EmbeddingProvider):
    provider_name = "local"

    def __init__(self, model: Optional[str] = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is not installed. Run "
                "`pip install sentence-transformers` before selecting "
                "embedding_provider=local (this pulls in torch — several "
                "hundred MB — which is why it isn't a core dependency)."
            ) from e

        self.model_name = model or settings.local_embedding_model
        self._model = SentenceTransformer(self.model_name)
        self.dimension = self._model.get_sentence_embedding_dimension()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # sentence-transformers' .encode() is synchronous, CPU-bound work —
        # run it off the event loop so it doesn't block other requests.
        embeddings = await asyncio.to_thread(self._model.encode, texts, convert_to_numpy=True)
        return [vec.tolist() for vec in embeddings]


_PROVIDERS = {
    "openai": OpenAIEmbeddingProvider,
    "voyage": VoyageEmbeddingProvider,
    "local": LocalEmbeddingProvider,
}


def get_embedding_provider(name: Optional[str] = None) -> EmbeddingProvider:
    key = (name or settings.embedding_provider).strip().lower()
    provider_cls = _PROVIDERS.get(key)
    if provider_cls is None:
        raise ValueError(f"Unknown embedding_provider '{key}'. Valid options: {sorted(_PROVIDERS)}")
    return provider_cls()


_DEFAULT_MODEL_NAMES = {
    "openai": lambda: settings.openai_embedding_model,
    "voyage": lambda: settings.voyage_embedding_model,
    "local": lambda: settings.local_embedding_model,
}


def get_active_provider_model(name: Optional[str] = None) -> tuple[str, str]:
    """(provider, model) for the currently configured embedding_provider —
    without instantiating it (no API key/heavy-dependency check needed just
    to know what to filter document_embeddings by)."""
    key = (name or settings.embedding_provider).strip().lower()
    if key not in _DEFAULT_MODEL_NAMES:
        raise ValueError(f"Unknown embedding_provider '{key}'. Valid options: {sorted(_PROVIDERS)}")
    return key, _DEFAULT_MODEL_NAMES[key]()
