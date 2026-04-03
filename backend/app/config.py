from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "AI Memory Layer"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://memuser:mempass@localhost:5432/aimemory",
        alias="DATABASE_URL",
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_cache_ttl: int = 3600  # 1 hour

    # Security
    secret_key: str = Field(
        default="change-this-in-production-use-32-byte-random-string",
        alias="SECRET_KEY",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption
    encryption_key: Optional[str] = Field(default=None, alias="ENCRYPTION_KEY")

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Local embeddings fallback
    use_local_embeddings: bool = False
    local_embedding_model: str = "all-MiniLM-L6-v2"
    local_embedding_dimensions: int = 384

    # Memory pipeline
    max_chunk_size: int = 512  # tokens
    chunk_overlap: int = 50
    max_context_memories: int = 5
    similarity_threshold: float = 0.7

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1", alias="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND"
    )

    # CORS
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "chrome-extension://*",
    ]

    class Config:
        env_file = ".env"
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
