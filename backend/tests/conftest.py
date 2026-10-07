"""Shared test fixtures. The LLM is always the scripted fake (see fake_llm.py), never a real model."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.services.debugger import DebugService
from app.services.history import HistoryStore
from app.tools.code_executor import SubprocessExecutor
from tests.fake_llm import ScriptedLLM, load_bugs


@pytest.fixture(scope="session")
def bugs() -> dict[str, dict]:
    return {b["id"]: b for b in load_bugs()}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="test-key",
        execution_timeout=2.0,
        max_attempts=3,
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
    )


@pytest.fixture
def executor(settings: Settings) -> SubprocessExecutor:
    return SubprocessExecutor(settings)


@pytest.fixture
def make_service(settings: Settings, executor: SubprocessExecutor, tmp_path: Path):
    def _make(llm: ScriptedLLM | None = None, configured: bool = True) -> DebugService:
        client = (llm or ScriptedLLM()).client() if configured else None
        return DebugService(settings, executor, HistoryStore(tmp_path / "svc.db"), client)

    return _make


def traceback_for(bug: dict) -> str:
    """A realistic error string for a fixture (what a user would paste)."""
    kinds = {
        "index_error_basic": 'Traceback (most recent call last):\n  File "main.py", line 4, in <module>\n    print(numbers[i])\nIndexError: list index out of range',
        "chained_two_bugs": 'Traceback (most recent call last):\n  File "main.py", line 5, in <module>\n    total += marks["scores"][i]\nIndexError: list index out of range',
    }
    return kinds[bug["id"]]
