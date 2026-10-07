"""Explicit agent state. Everything the agent knows lives here, so it is easy to inspect."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.tools.code_executor import Executor
from app.models.schemas import (
    Attempt,
    CodeAnalysis,
    DiffResult,
    Explanation,
    ToolCall,
    WhyItWorked,
)

Emit = Callable[[dict], None]


def _noop(_: dict) -> None:
    return None


@dataclass
class AgentState:
    # --- inputs ---
    code: str
    error: str
    language: str = "python"
    explanation_mode: str = "cs_student"
    expected_output: str | None = None

    # --- reasoning outputs ---
    analysis: CodeAnalysis | None = None
    explanation: Explanation | None = None
    current_fix: str | None = None  # last candidate the agent executed
    diagnosis: str = ""
    changes: list[str] = field(default_factory=list)
    reasoning: str = ""
    diff: DiffResult | None = None

    # --- observations ---
    execution_output: str = ""  # stdout of the latest execution
    execution_error: str = ""  # stderr (or timeout note) of the latest execution
    attempts: list[Attempt] = field(default_factory=list)
    max_attempts: int = 3
    fix_verified: bool = False

    # --- teaching outputs ---
    why_it_worked: WhyItWorked | None = None
    concepts: list[str] = field(default_factory=list)

    # --- bookkeeping ---
    tool_trace: list[ToolCall] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    analyzed_since_last_run: bool = False

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def attempts_left(self) -> int:
        return max(0, self.max_attempts - self.attempt_count)


@dataclass
class AgentContext:
    """Passed to every tool call through the Agents SDK's RunContextWrapper."""

    state: AgentState
    executor: Executor
    emit: Emit = _noop
