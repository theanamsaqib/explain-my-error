"""Application settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# Later files do not override earlier ones or real environment variables.
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- LLM (any OpenAI-compatible provider) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""  # empty = official OpenAI endpoint
    llm_timeout: float = 60.0

    # --- Agent ---
    max_attempts: int = 3

    # --- Code execution ---
    execution_backend: str = "subprocess"  # "subprocess" or "docker"
    execution_timeout: float = 5.0
    max_output_size: int = 10_000  # bytes kept per stream (stdout / stderr)
    execution_memory_mb: int = 512
    docker_image: str = "python:3.12-slim"
    max_concurrent_executions: int = 4

    # --- Storage ---
    database_url: str = "sqlite:///./data/debug_history.db"

    # --- Web ---
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: ("http://localhost:3000", "http://127.0.0.1:3000")
    )

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def database_path(self) -> Path:
        """Filesystem path of the SQLite database (from a sqlite:/// URL)."""
        url = self.database_url.strip()
        prefix = "sqlite:///"
        raw = url[len(prefix):] if url.startswith(prefix) else url
        path = Path(raw)
        if not path.is_absolute():
            path = _BACKEND_DIR / path
        return path


def load_settings() -> Settings:
    origins = tuple(
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if o.strip()
    )
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini",
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        llm_timeout=_float("LLM_TIMEOUT", 60.0),
        max_attempts=max(1, min(_int("MAX_ATTEMPTS", 3), 5)),
        execution_backend=os.getenv("EXECUTION_BACKEND", "subprocess").strip().lower() or "subprocess",
        execution_timeout=max(0.5, _float("EXECUTION_TIMEOUT", 5.0)),
        max_output_size=max(256, _int("MAX_OUTPUT_SIZE", 10_000)),
        execution_memory_mb=max(64, _int("EXECUTION_MEMORY_MB", 512)),
        docker_image=os.getenv("DOCKER_IMAGE", "python:3.12-slim").strip() or "python:3.12-slim",
        max_concurrent_executions=max(1, _int("MAX_CONCURRENT_EXECUTIONS", 4)),
        database_url=os.getenv("DATABASE_URL", "").strip() or "sqlite:///./data/debug_history.db",
        cors_origins=origins,
    )
