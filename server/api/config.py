from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from pydantic import BaseModel, field_validator

try:
    from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
except ImportError:  # pragma: no cover - fallback for lean local environments
    BaseSettings = BaseModel  # type: ignore[assignment]
    NoDecode = list[str]  # type: ignore[assignment]

    def SettingsConfigDict(**kwargs):  # type: ignore[override]
        return kwargs


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    database_url: str = 'sqlite+aiosqlite:///./omniroute.db'
    cors_allow_origins: Annotated[list[str], NoDecode] = ['http://localhost:5173', 'http://127.0.0.1:5173']

    embedding_provider: str = 'openai'
    embedding_model: str = 'text-embedding-3-small'
    embedding_dim: int = 1536
    embedding_api_key: str = ''
    embedding_base_url: str = 'https://api.openai.com/v1'
    embedding_batch_size: int = 32
    embedding_timeout_seconds: int = 30

    llm_provider: str = 'openai'
    llm_model: str = 'gpt-4o-mini'
    llm_api_key: str = ''
    llm_base_url: str = 'https://api.openai.com/v1'
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 30
    crewai_enabled: bool = True
    langsmith_tracing: bool = False
    langsmith_api_key: str = ''
    langsmith_endpoint: str = 'https://api.smith.langchain.com'
    langsmith_project: str = 'omniroute'
    langsmith_workspace_id: str = ''

    @classmethod
    def from_env(cls) -> 'Settings':
        return cls(
            database_url=os.getenv('DATABASE_URL', cls.model_fields['database_url'].default),
            cors_allow_origins=_parse_csv(os.getenv('CORS_ALLOW_ORIGINS'), cls.model_fields['cors_allow_origins'].default),
            embedding_provider=os.getenv('EMBEDDING_PROVIDER', cls.model_fields['embedding_provider'].default),
            embedding_model=os.getenv('EMBEDDING_MODEL', cls.model_fields['embedding_model'].default),
            embedding_dim=_parse_int(os.getenv('EMBEDDING_DIM'), cls.model_fields['embedding_dim'].default),
            embedding_api_key=os.getenv('EMBEDDING_API_KEY', cls.model_fields['embedding_api_key'].default),
            embedding_base_url=os.getenv('EMBEDDING_BASE_URL', cls.model_fields['embedding_base_url'].default),
            embedding_batch_size=_parse_int(os.getenv('EMBEDDING_BATCH_SIZE'), cls.model_fields['embedding_batch_size'].default),
            embedding_timeout_seconds=_parse_int(
                os.getenv('EMBEDDING_TIMEOUT_SECONDS'),
                cls.model_fields['embedding_timeout_seconds'].default,
            ),
            llm_provider=os.getenv('LLM_PROVIDER', cls.model_fields['llm_provider'].default),
            llm_model=os.getenv('LLM_MODEL', cls.model_fields['llm_model'].default),
            llm_api_key=os.getenv('LLM_API_KEY', cls.model_fields['llm_api_key'].default),
            llm_base_url=os.getenv('LLM_BASE_URL', cls.model_fields['llm_base_url'].default),
            llm_temperature=_parse_float(os.getenv('LLM_TEMPERATURE'), cls.model_fields['llm_temperature'].default),
            llm_timeout_seconds=_parse_int(os.getenv('LLM_TIMEOUT_SECONDS'), cls.model_fields['llm_timeout_seconds'].default),
            crewai_enabled=_parse_bool(os.getenv('CREWAI_ENABLED'), cls.model_fields['crewai_enabled'].default),
            langsmith_tracing=_parse_bool(os.getenv('LANGSMITH_TRACING'), cls.model_fields['langsmith_tracing'].default),
            langsmith_api_key=os.getenv('LANGSMITH_API_KEY', cls.model_fields['langsmith_api_key'].default),
            langsmith_endpoint=os.getenv('LANGSMITH_ENDPOINT', cls.model_fields['langsmith_endpoint'].default),
            langsmith_project=os.getenv('LANGSMITH_PROJECT', cls.model_fields['langsmith_project'].default),
            langsmith_workspace_id=os.getenv('LANGSMITH_WORKSPACE_ID', cls.model_fields['langsmith_workspace_id'].default),
        )

    @field_validator('cors_allow_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, value):
        return _parse_csv(value, ['http://localhost:5173', 'http://127.0.0.1:5173'])

    @field_validator('embedding_provider', mode='before')
    @classmethod
    def normalize_embedding_provider(cls, value: str | None) -> str:
        provider = str(value or 'openai').strip().lower()
        if provider not in {'openai', 'openai_compatible'}:
            return 'openai'
        return provider

    @field_validator('llm_provider', mode='before')
    @classmethod
    def normalize_llm_provider(cls, value: str | None) -> str:
        provider = str(value or 'openai').strip().lower()
        if provider not in {'openai', 'openai_compatible'}:
            return 'openai'
        return provider

    @field_validator('embedding_batch_size', 'embedding_timeout_seconds', mode='before')
    @classmethod
    def min_embedding_positive(cls, value: int | str) -> int:
        return max(1, _parse_int(value, 1))

    @field_validator('llm_timeout_seconds', mode='before')
    @classmethod
    def min_llm_timeout_positive(cls, value: int | str) -> int:
        return max(1, _parse_int(value, 1))

    @field_validator('llm_temperature', mode='before')
    @classmethod
    def normalize_llm_temperature(cls, value: float | int | str) -> float:
        return max(0.0, min(_parse_float(value, 0.0), 2.0))

    @field_validator('crewai_enabled', 'langsmith_tracing', mode='before')
    @classmethod
    def normalize_bool_flags(cls, value: bool | str | int | None) -> bool:
        return _parse_bool(value, False)


def _parse_csv(value, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(',') if part.strip()]


def _parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _parse_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _parse_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


@lru_cache
def get_settings() -> Settings:
    if BaseSettings is BaseModel:
        return Settings.from_env()
    return Settings()
