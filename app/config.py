"""Application configuration loaded strictly from environment variables."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for Grounded Documentation Assistant."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    PORT: int = Field(default=8080, description="HTTP server port")
    HOST: str = Field(default="0.0.0.0", description="HTTP server bind host")

    # Ollama / LLM settings (8 GB RAM constrained: qwen2.5:3b, num_ctx 4096)
    OLLAMA_HOST: str = Field(
        default="http://localhost:11434",
        description="Base URL for Ollama service",
    )
    LLM_MODEL: str = Field(
        default="qwen2.5:3b",
        description="LLM model identifier for generation (qwen2.5:3b for 8GB RAM)",
    )
    NUM_CTX: int = Field(
        default=4096,
        description="Ollama context window length",
    )
    NUM_PREDICT: int = Field(
        default=300,
        description="Ollama maximum output tokens to predict",
    )
    KEEP_ALIVE: str = Field(
        default="5m",
        description="Ollama model keep_alive duration",
    )
    OLLAMA_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Timeout in seconds for LLM generation requests",
    )
    REFUSE_MIN_SCORE: float = Field(
        default=0.60,
        description="Minimum retrieval similarity score threshold for refusal (chosen from DEV)",
    )
    REL_MIN_COVERAGE: float = Field(
        default=0.40,
        description="Minimum weighted relevance coverage threshold for evidence (chosen from DEV)",
    )

    # Embedding & Storage settings
    EMBED_MODEL: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Sentence-transformers embedding model name or path",
    )
    INDEX_DIR: str = Field(
        default="index",
        description="Directory for vector database index storage",
    )
    CHUNKS_PATH: str = Field(
        default="index/chunks.jsonl",
        description="Path to JSONL sidecar containing exact raw chunk text",
    )
    CORPUS_DIR: str = Field(
        default="corpus",
        description="Root directory for markdown corpus files",
    )

    # Retrieval settings
    RETRIEVER: str = Field(
        default="dense",
        description="Retriever type: 'dense' or 'hybrid'",
    )
    RERANKER: str = Field(
        default="none",
        description="Reranker type: 'none' or 'bge'",
    )
    TOP_K_DEFAULT: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Default number of chunks to retrieve",
    )

    # Refusal Layer 1 thresholds
    THRESHOLD_MIN: float = Field(
        default=0.60,
        description="Minimum similarity score required for retrieval confidence",
    )
    MIN_SUPPORTING_CHUNKS: int = Field(
        default=1,
        ge=1,
        description="Minimum number of chunks required above lower score bar",
    )
    MIN_SUPPORT: float = Field(
        default=0.50,
        description="Minimum content-word support fraction for an answer sentence to be retained (chosen from DEV)",
    )

    # Request timeouts & limits
    REQUEST_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Global timeout for incoming API requests in seconds",
    )
    MAX_QUESTION_LENGTH: int = Field(
        default=4000,
        description="Maximum accepted characters for input question before safe truncation",
    )

    @property
    def index_path(self) -> Path:
        return Path(self.INDEX_DIR)

    @property
    def chunks_file(self) -> Path:
        return Path(self.CHUNKS_PATH)

    @property
    def corpus_path(self) -> Path:
        return Path(self.CORPUS_DIR)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of runtime settings."""
    return Settings()
