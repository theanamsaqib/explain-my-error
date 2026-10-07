"""Pydantic schemas: API request/response contract and LLM output shapes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ExplanationMode = Literal["eli5", "cs_student", "interview", "technical"]
DebugMode = Literal["explain", "fix"]
DebugStatus = Literal["explained", "fixed", "failed", "no_error", "error"]


# --------------------------------------------------------------------------- request
class DebugRequest(BaseModel):
    mode: DebugMode
    code: str = Field(..., max_length=20_000)
    error: str = Field("", max_length=10_000)
    language: str = "python"
    explanation_mode: ExplanationMode = "cs_student"
    # Optional: if given, a fix only counts as successful when stdout matches.
    expected_output: str | None = Field(None, max_length=10_000)

    @field_validator("code")
    @classmethod
    def code_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Please paste some code first.")
        return v

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        return v.strip().lower() or "python"


# --------------------------------------------------------------------------- tools
class ExecutionResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    output_truncated: bool = False
    duration_ms: int = 0
    note: str = ""


class SuspiciousLine(BaseModel):
    line: int
    code: str
    reason: str


class CodeAnalysis(BaseModel):
    error_type: str = "Unknown"
    error_message: str = ""
    line_number: int | None = None
    suspicious_lines: list[SuspiciousLine] = []
    likely_cause: str = ""
    concept_hint: str = ""
    syntax_ok: bool = True


class DiffLine(BaseModel):
    type: Literal["add", "remove", "context"]
    text: str
    old_no: int | None = None
    new_no: int | None = None


class DiffResult(BaseModel):
    unified_diff: str
    lines: list[DiffLine]
    added: int
    removed: int
    changed: bool


# --------------------------------------------------------------------------- LLM outputs
class ExplanationOut(BaseModel):
    """What the explainer LLM must return."""

    error_type: str = ""
    summary: str = ""  # one or two sentences: what went wrong
    explanation: str = ""  # what / where / why, in the requested style (markdown ok)
    concept: str = ""
    problematic_lines: list[int] = []
    example: str | None = None


class FixOut(BaseModel):
    """What the fixer agent returns as its final message."""

    diagnosis: str = ""
    fixed_code: str = ""
    changes: list[str] = []
    reasoning: str = ""


class WhyItWorked(BaseModel):
    what_was_wrong: str = ""
    what_changed: str = ""
    why_it_worked: str = ""
    concepts: list[str] = []
    remember: str = ""


# --------------------------------------------------------------------------- response
class Explanation(BaseModel):
    error_type: str
    summary: str
    explanation: str
    concept: str
    problematic_lines: list[int] = []
    problematic_code: str = ""
    example: str | None = None
    source: Literal["llm", "static"] = "llm"


class Attempt(BaseModel):
    number: int
    analyzed: bool = False  # was analyze_code called before this attempt?
    rationale: str = ""  # the agent's stated reason for this candidate fix
    code: str
    execution: ExecutionResult
    success: bool
    observation: str = ""  # short human summary of what the agent observed
    source: Literal["agent", "orchestrator"] = "agent"


class FixResult(BaseModel):
    diagnosis: str = ""
    fixed_code: str = ""
    changes: list[str] = []
    reasoning: str = ""
    diff: DiffResult | None = None
    verified: bool = False


class ToolCall(BaseModel):
    tool: str
    summary: str
    ok: bool = True
    by: Literal["agent", "orchestrator"] = "agent"


class DebugResponse(BaseModel):
    id: int | None = None
    mode: DebugMode
    status: DebugStatus
    error_type: str = ""
    message: str = ""  # human-readable status / failure summary
    explanation: Explanation | None = None
    fix: FixResult | None = None
    attempts: list[Attempt] = []
    max_attempts: int = 3
    why_it_worked: WhyItWorked | None = None
    tool_trace: list[ToolCall] = []
    warnings: list[str] = []
    # Echoed back so a stored session can be reopened in the editor.
    code: str = ""
    error: str = ""
    explanation_mode: ExplanationMode = "cs_student"


class HistoryItem(BaseModel):
    id: int
    created_at: str
    mode: DebugMode
    status: DebugStatus
    error_type: str
    preview: str


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_configured: bool
    model: str
    execution_backend: str
    max_attempts: int


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
