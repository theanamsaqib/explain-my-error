"""The agent layer: LLM connection, the three tools, and helpers that record what happened.

Built on the OpenAI Agents SDK. Any OpenAI-compatible provider works because we talk to it through
the Chat Completions API with a configurable base URL.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

import openai
from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    RunContextWrapper,
    function_tool,
    set_tracing_disabled,
)
from agents.exceptions import MaxTurnsExceeded
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.agent import prompts
from app.agent.state import AgentContext, AgentState
from app.config import Settings
from app.errors import LLMError
from app.models.schemas import Attempt, ToolCall
from app.tools.code_analyzer import analyze_code
from app.tools.code_executor import compare_output
from app.tools.diff_generator import generate_diff

# Tracing would try to upload to the OpenAI platform; it is off for a local college project.
set_tracing_disabled(True)

T = TypeVar("T", bound=BaseModel)


# ------------------------------------------------------------------ LLM connection
def build_llm_client(settings: Settings) -> AsyncOpenAI | None:
    if not settings.llm_configured:
        return None
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.llm_timeout,
        max_retries=1,
    )


def build_model(settings: Settings, client: AsyncOpenAI) -> OpenAIChatCompletionsModel:
    return OpenAIChatCompletionsModel(model=settings.openai_model, openai_client=client)


def to_llm_error(exc: Exception) -> LLMError:
    """Translate any provider / SDK failure into a friendly error (no stack traces)."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return LLMError("llm_auth", "The LLM provider rejected the API key. Check OPENAI_API_KEY.", 502)
    if isinstance(exc, openai.RateLimitError):
        return LLMError("llm_rate_limit", "The LLM provider is rate-limiting requests. Wait a moment and retry.", 429)
    if isinstance(exc, openai.NotFoundError):
        return LLMError("llm_model", "The LLM provider does not know this model. Check OPENAI_MODEL.", 502)
    if isinstance(exc, openai.APITimeoutError):
        return LLMError("llm_timeout", "The LLM provider took too long to answer.", 504)
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("llm_unreachable", "Could not reach the LLM provider. Check your network and OPENAI_BASE_URL.", 502)
    if isinstance(exc, openai.APIStatusError):
        return LLMError("llm_api", f"The LLM provider returned an error (HTTP {exc.status_code}).", 502)
    if isinstance(exc, MaxTurnsExceeded):
        return LLMError("agent_max_turns", "The agent ran out of steps before finishing.", 502)
    return LLMError("llm_failed", "The AI agent failed unexpectedly.", 502)


# ------------------------------------------------------------------ robust JSON handling
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of an LLM reply, tolerating code fences and surrounding prose."""
    cleaned = _FENCE.sub("", (text or "").strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found") from None
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    return data


def parse_llm_json(model_cls: type[T], text: str) -> T:
    try:
        return model_cls.model_validate(extract_json(text))
    except (ValueError, ValidationError) as exc:
        raise LLMError("llm_malformed", "The AI returned a response in an unexpected format.", 502) from exc


# ------------------------------------------------------------------ recording actions + observations
def log_tool(ctx: AgentContext, tool: str, summary: str, ok: bool = True, by: str = "agent") -> None:
    ctx.state.tool_trace.append(ToolCall(tool=tool, summary=summary, ok=ok, by=by))  # type: ignore[arg-type]
    ctx.emit({"type": "tool_call", "tool": tool, "summary": summary, "ok": ok, "by": by})


def _observation(result_stderr: str, note: str, stdout: str, success: bool, matches: bool | None) -> str:
    if success:
        first = next((ln for ln in stdout.splitlines() if ln.strip()), "")
        base = "Ran cleanly (exit code 0)"
        if matches is True:
            base += " and the output matches the expected output"
        return f"{base}. Output starts with: {first[:80]}" if first else f"{base}."
    if matches is False and not result_stderr and not note:
        return "Ran without errors but the output did not match the expected output."
    if note and "timed out" in note:
        return note
    last = next((ln for ln in reversed(result_stderr.splitlines()) if ln.strip()), "")
    return last or note or "Failed with no error text."


async def run_attempt(ctx: AgentContext, code: str, rationale: str, source: str = "agent") -> Attempt:
    """ACT + OBSERVE: execute a candidate fix, record the observation, update the state."""
    st: AgentState = ctx.state
    number = st.attempt_count + 1
    ctx.emit({"type": "attempt_running", "attempt": number, "rationale": rationale, "code": code})

    result = await ctx.executor.run(code)
    matches = compare_output(result.stdout, st.expected_output)
    success = result.success and matches is not False

    attempt = Attempt(
        number=number,
        analyzed=st.analyzed_since_last_run,
        rationale=rationale,
        code=code,
        execution=result,
        success=success,
        observation=_observation(result.stderr, result.note, result.stdout, success, matches),
        source=source,  # type: ignore[arg-type]
    )
    st.attempts.append(attempt)
    st.current_fix = code
    st.execution_output = result.stdout
    st.execution_error = result.stderr or result.note
    st.fix_verified = success
    st.analyzed_since_last_run = False
    st.tool_trace.append(
        ToolCall(
            tool="execute_python",
            summary=f"attempt {number}: {'passed' if success else 'failed'} - {attempt.observation[:90]}",
            ok=success,
            by=source,  # type: ignore[arg-type]
        )
    )
    ctx.emit({"type": "attempt_result", "attempt": number, "data": attempt.model_dump()})
    if not success and st.attempts_left > 0:
        ctx.emit({"type": "attempt_started", "attempt": number + 1})
    return attempt


# ------------------------------------------------------------------ the three tools
@function_tool(name_override="analyze_code")
def analyze_code_tool(ctx: RunContextWrapper[AgentContext], code: str, error: str) -> str:
    """Statically analyze Python source code together with an error message.

    Returns JSON with the error type, the failing line number, suspicious lines with reasons,
    the likely cause and the programming concept involved. Use it to understand a new failure.

    Args:
        code: The Python source code to analyze.
        error: The error message / traceback (or program output) to analyze it against.
    """
    context = ctx.context
    analysis = analyze_code(code, error)
    context.state.analyzed_since_last_run = True
    log_tool(context, "analyze_code", f"{analysis.error_type} at line {analysis.line_number}: {analysis.likely_cause[:80]}")
    return analysis.model_dump_json()


@function_tool(name_override="execute_python")
async def execute_python_tool(ctx: RunContextWrapper[AgentContext], code: str, rationale: str) -> str:
    """Run a complete Python program in a sandbox and observe the result.

    Returns JSON: success, stdout, stderr, exit_code, timed_out, plus attempts_remaining.
    Only the standard library is available, there is no network and stdin is closed.

    Args:
        code: The COMPLETE Python program to run (not a snippet).
        rationale: One or two sentences: what you changed in this candidate and why.
    """
    context = ctx.context
    st = context.state
    if st.attempts_left <= 0:
        log_tool(context, "execute_python", "refused: attempt budget exhausted", ok=False)
        return json.dumps(
            {
                "error": "attempt_limit_reached",
                "message": "No execution attempts left. Stop calling tools and give your final answer.",
            }
        )
    attempt = await run_attempt(context, code, rationale, source="agent")
    ex = attempt.execution
    payload: dict[str, Any] = {
        "attempt": attempt.number,
        "attempts_remaining": st.attempts_left,
        "success": attempt.success,
        "stdout": ex.stdout,
        "stderr": ex.stderr,
        "exit_code": ex.exit_code,
        "timed_out": ex.timed_out,
        "output_truncated": ex.output_truncated,
        "note": ex.note,
    }
    matches = compare_output(ex.stdout, st.expected_output)
    if matches is not None:
        payload["matches_expected"] = matches
    if not attempt.success and st.attempts_left == 0:
        payload["message"] = "No attempts left. Stop and explain what you learned in your final answer."
    return json.dumps(payload)


@function_tool(name_override="generate_diff")
def generate_diff_tool(ctx: RunContextWrapper[AgentContext], original: str, fixed: str) -> str:
    """Create a unified diff between the original code and the fixed code.

    Args:
        original: The original (buggy) source code.
        fixed: The corrected source code.
    """
    context = ctx.context
    diff = generate_diff(original, fixed)
    context.state.diff = diff
    log_tool(context, "generate_diff", f"+{diff.added} / -{diff.removed} lines")
    return json.dumps({"unified_diff": diff.unified_diff, "added": diff.added, "removed": diff.removed})


# ------------------------------------------------------------------ agents
def build_fix_agent(settings: Settings, model: OpenAIChatCompletionsModel) -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="Debugger",
        instructions=prompts.fix_system(settings.max_attempts),
        tools=[analyze_code_tool, execute_python_tool, generate_diff_tool],
        model=model,
    )


def build_explainer_agent(mode: str, model: OpenAIChatCompletionsModel) -> Agent[None]:
    return Agent(name="Explainer", instructions=prompts.explain_system(mode), model=model)


def build_why_agent(mode: str, model: OpenAIChatCompletionsModel) -> Agent[None]:
    return Agent(name="Tutor", instructions=prompts.why_system(mode), model=model)
