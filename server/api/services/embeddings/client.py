from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...config import Settings, get_settings

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - import guard for environments without dependency.
    AsyncOpenAI = None  # type: ignore[assignment]


SUPPORTED_EMBEDDING_PROVIDERS = {'openai', 'openai_compatible'}


@dataclass(frozen=True, slots=True)
class EmbeddingClientConfig:
    provider: str
    model: str
    dim: int
    api_key: str
    base_url: str
    batch_size: int
    timeout_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> EmbeddingClientConfig:
        current_settings = settings or get_settings()
        provider = (current_settings.embedding_provider or 'openai').strip().lower()
        if provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            allowed = ', '.join(sorted(SUPPORTED_EMBEDDING_PROVIDERS))
            raise ValueError(f'Unsupported embedding provider: {provider}. Allowed values: {allowed}.')

        return cls(
            provider=provider,
            model=(current_settings.embedding_model or '').strip(),
            dim=current_settings.embedding_dim,
            api_key=(current_settings.embedding_api_key or '').strip(),
            base_url=(current_settings.embedding_base_url or '').strip(),
            batch_size=max(1, current_settings.embedding_batch_size),
            timeout_seconds=max(1, current_settings.embedding_timeout_seconds),
        )


def embeddings_enabled(settings: Settings | None = None) -> bool:
    current_settings = settings or get_settings()
    provider = (current_settings.embedding_provider or '').strip().lower()
    model = (current_settings.embedding_model or '').strip()
    return provider in SUPPORTED_EMBEDDING_PROVIDERS and bool(model)


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        config: EmbeddingClientConfig | None = None,
        *,
        openai_client: Any | None = None,
    ) -> None:
        self.config = config or EmbeddingClientConfig.from_settings()
        if openai_client is not None:
            self._client = openai_client
            return
        if AsyncOpenAI is None:
            raise RuntimeError('openai package is required for embedding support.')
        self._client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=float(self.config.timeout_seconds),
        )

    async def embed_text(self, text: str) -> list[float]:
        embeddings = await self.embed_texts([text])
        if not embeddings:
            raise RuntimeError('Embedding provider returned an empty embedding list.')
        return embeddings[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.config.provider == 'openai' and not self.config.api_key:
            raise RuntimeError('EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=openai.')

        cleaned_texts = [str(item or '').strip() for item in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned_texts), self.config.batch_size):
            batch = cleaned_texts[start : start + self.config.batch_size]
            response = await self._client.embeddings.create(  # type: ignore[union-attr]
                model=self.config.model,
                input=batch,
            )
            vectors.extend([list(item.embedding) for item in response.data])

        if len(vectors) != len(cleaned_texts):
            raise RuntimeError('Embedding response size mismatch.')
        return vectors


@lru_cache
def get_embedding_client() -> OpenAICompatibleEmbeddingClient:
    return OpenAICompatibleEmbeddingClient()
