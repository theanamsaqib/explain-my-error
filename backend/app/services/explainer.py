"""Task 1: "Explain My Error". Static analysis tool call first, then an LLM explanation."""

from __future__ import annotations

from agents import Runner
from openai import AsyncOpenAI  # noqa: F401  (re-exported type for readers)

from app.agent import prompts
from app.agent.agent import build_explainer_agent, parse_llm_json, to_llm_error
from app.agent.state import AgentState
from app.errors import LLMError
from app.models.schemas import CodeAnalysis, Explanation, ExplanationOut


def snippet(code: str, lines: list[int]) -> str:
    src = code.splitlines()
    picked = sorted({n for n in lines if 1 <= n <= len(src)})
    return "\n".join(f"{n:>3} | {src[n - 1]}" for n in picked)


def static_explanation(code: str, analysis: CodeAnalysis) -> Explanation:
    """Fallback used when the LLM is unavailable: built purely from the static analysis."""
    bullets = "\n".join(f"- line {s.line}: {s.reason}" for s in analysis.suspicious_lines)
    lines = [s.line for s in analysis.suspicious_lines]
    return Explanation(
        error_type=analysis.error_type,
        summary=f"{analysis.error_type}: {analysis.error_message}".strip(": "),
        explanation=f"**Likely cause:** {analysis.likely_cause}\n\n**Suspicious lines**\n{bullets}".strip(),
        concept=analysis.concept_hint,
        problematic_lines=lines[:3],
        problematic_code=snippet(code, lines[:3]),
        source="static",
    )


async def explain_error(state: AgentState, model) -> Explanation:
    assert state.analysis is not None
    agent = build_explainer_agent(state.explanation_mode, model)

    out: ExplanationOut | None = None
    last_error: LLMError | None = None
    for _ in range(2):  # one retry if the model answers in the wrong format
        try:
            result = await Runner.run(agent, prompts.explain_user(state), max_turns=2)
            out = parse_llm_json(ExplanationOut, str(result.final_output))
            break
        except LLMError as exc:
            last_error = exc
        except Exception as exc:  # provider / SDK failure
            last_error = to_llm_error(exc)
            break

    if out is None:
        assert last_error is not None
        state.warnings.append(f"{last_error.message} Showing the built-in static analysis instead.")
        return static_explanation(state.code, state.analysis)

    n_lines = len(state.code.splitlines())
    lines = [n for n in out.problematic_lines if 1 <= n <= n_lines] or [
        s.line for s in state.analysis.suspicious_lines[:2]
    ]
    return Explanation(
        error_type=out.error_type.strip() or state.analysis.error_type,
        summary=out.summary.strip() or state.analysis.likely_cause,
        explanation=out.explanation.strip() or state.analysis.likely_cause,
        concept=out.concept.strip() or state.analysis.concept_hint,
        problematic_lines=lines,
        problematic_code=snippet(state.code, lines),
        example=(out.example or None),
        source="llm",
    )
