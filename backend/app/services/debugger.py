"""Task 2: "Fix My Code": the orchestrator that runs the full agentic loop.

Flow (see docs/agent-workflow.md):
  receive code + error -> analyze_code -> [LLM agent: generate fix -> execute_python -> observe
  -> (fail: analyze_code again -> new fix -> execute again, max N attempts)] -> verify ->
  generate_diff -> "Why did my fix work?" -> response.

The LLM drives the ReAct loop through tool calls; this module owns the guard rails: the attempt
budget, the ground truth about success (taken from the sandbox, never from the LLM's words),
fallbacks and the final response.
"""

from __future__ import annotations

import logging

from agents import Runner
from openai import AsyncOpenAI

from app.agent import prompts
from app.agent.agent import (
    build_fix_agent,
    build_model,
    build_why_agent,
    log_tool,
    parse_llm_json,
    run_attempt,
    to_llm_error,
)
from app.agent.state import AgentContext, AgentState, Emit, _noop
from app.config import Settings
from app.errors import AppError, LLMError
from app.models.schemas import (
    DebugRequest,
    DebugResponse,
    Explanation,
    FixOut,
    FixResult,
    WhyItWorked,
)
from app.services.explainer import explain_error, static_explanation
from app.services.history import HistoryStore
from app.tools.code_analyzer import analyze_code
from app.tools.code_executor import Executor, compare_output
from app.tools.diff_generator import generate_diff

log = logging.getLogger("explain_my_error")


class DebugService:
    def __init__(
        self,
        settings: Settings,
        executor: Executor,
        history: HistoryStore,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.executor = executor
        self.history = history
        self.model = build_model(settings, llm_client) if llm_client is not None else None

    # ------------------------------------------------------------------ entry point
    async def handle(self, req: DebugRequest, emit: Emit = _noop) -> DebugResponse:
        if req.language != "python":
            raise AppError("unsupported_language", f"'{req.language}' is not supported yet. Only Python is supported.", 400)

        state = AgentState(
            code=req.code,
            error=req.error.strip(),
            language=req.language,
            explanation_mode=req.explanation_mode,
            expected_output=req.expected_output,
            max_attempts=self.settings.max_attempts,
        )
        ctx = AgentContext(state=state, executor=self.executor, emit=emit)

        early = await self._ensure_error(ctx, req.mode)
        if early is not None:
            return await self._finish(early)

        emit({"type": "status", "stage": "analyzing", "message": "Analyzing your code..."})
        state.analysis = analyze_code(state.code, state.error)
        state.analyzed_since_last_run = True
        log_tool(
            ctx, "analyze_code",
            f"{state.analysis.error_type} at line {state.analysis.line_number}: {state.analysis.likely_cause[:80]}",
            by="orchestrator",
        )

        if req.mode == "explain":
            response = await self._explain(ctx)
        else:
            response = await self._fix(ctx)
        return await self._finish(response)

    # ------------------------------------------------------------------ explain
    async def _explain(self, ctx: AgentContext) -> DebugResponse:
        state = ctx.state
        ctx.emit({"type": "status", "stage": "explaining", "message": "Writing the explanation..."})
        if self.model is None:
            state.warnings.append("No LLM API key is configured, so this is the built-in static analysis only. Set OPENAI_API_KEY for full explanations.")
            state.explanation = static_explanation(state.code, state.analysis)  # type: ignore[arg-type]
        else:
            state.explanation = await explain_error(state, self.model)
        return self._response(state, "explain", "explained", "Explanation ready.")

    # ------------------------------------------------------------------ fix (the agent loop)
    async def _fix(self, ctx: AgentContext) -> DebugResponse:
        state = ctx.state
        if self.model is None:
            raise AppError("llm_not_configured", "Fixing code needs an LLM. Set OPENAI_API_KEY in your .env file and restart the backend.", 503)

        agent = build_fix_agent(self.settings, self.model)
        ctx.emit({"type": "attempt_started", "attempt": 1})
        final_text = ""
        try:
            result = await Runner.run(
                agent,
                prompts.fix_user(state),
                context=ctx,
                max_turns=state.max_attempts * 3 + 4,
            )
            final_text = str(result.final_output or "")
        except Exception as exc:
            err = to_llm_error(exc)
            log.warning("fix agent failed: %s (%s)", err.code, type(exc).__name__)
            if state.attempt_count == 0:
                raise err from exc
            state.warnings.append(f"{err.message} Showing the attempts completed so far.")

        fix_out = FixOut()
        try:
            fix_out = parse_llm_json(FixOut, final_text)
        except LLMError:
            if final_text.strip():
                state.warnings.append("The agent's final summary was malformed; using the recorded attempts instead.")

        # Guard rail: the agent must use the tool. If it only wrote code, we run that code ourselves.
        if state.attempt_count == 0:
            if not fix_out.fixed_code.strip():
                return self._response(state, "fix", "failed", "The agent did not produce a fix. Try again or simplify the code.")
            state.warnings.append("The agent proposed a fix without testing it, so the system executed it.")
            await run_attempt(ctx, fix_out.fixed_code, fix_out.reasoning or fix_out.diagnosis, source="orchestrator")

        last = state.attempts[-1]
        state.diagnosis = fix_out.diagnosis or last.rationale
        state.changes = fix_out.changes
        state.reasoning = fix_out.reasoning
        if fix_out.fixed_code.strip() and fix_out.fixed_code.strip() != (state.current_fix or "").strip():
            state.warnings.append("The agent's final answer differed from the last code it tested; showing the tested code.")

        # Ground truth = the sandbox result of the last executed code.
        state.fix_verified = last.success
        # Always diff the code that was actually verified (the agent may have diffed an earlier candidate).
        agent_diffed = any(t.tool == "generate_diff" for t in state.tool_trace)
        state.diff = generate_diff(state.code, state.current_fix or "")
        if not agent_diffed:
            log_tool(ctx, "generate_diff", f"+{state.diff.added} / -{state.diff.removed} lines", by="orchestrator")

        if state.fix_verified:
            ctx.emit({"type": "status", "stage": "teaching", "message": "Fix verified. Writing why it worked..."})
            state.why_it_worked = await self._why(state)
            state.concepts = state.why_it_worked.concepts
            n = state.attempt_count
            msg = f"Fix verified after {n} attempt{'s' if n != 1 else ''}."
            return self._response(state, "fix", "fixed", msg)

        msg = (
            f"Could not verify a fix after {state.attempt_count} attempt{'s' if state.attempt_count != 1 else ''}. "
            f"Last observation: {last.observation}"
        )
        if state.reasoning:
            msg += f" Agent's notes: {state.reasoning}"
        return self._response(state, "fix", "failed", msg)

    # ------------------------------------------------------------------ "Why did my fix work?"
    async def _why(self, state: AgentState) -> WhyItWorked:
        diff_text = state.diff.unified_diff if state.diff else ""
        if self.model is not None:
            agent = build_why_agent(state.explanation_mode, self.model)
            for _ in range(2):
                try:
                    result = await Runner.run(agent, prompts.why_user(state, diff_text), max_turns=2)
                    why = parse_llm_json(WhyItWorked, str(result.final_output))
                    if why.what_was_wrong and why.why_it_worked:
                        return why
                except LLMError:
                    continue
                except Exception as exc:
                    state.warnings.append(f"{to_llm_error(exc).message} Showing a simplified explanation.")
                    break
        return self._fallback_why(state)

    @staticmethod
    def _fallback_why(state: AgentState) -> WhyItWorked:
        a = state.analysis
        changed = "; ".join(state.changes) or (
            f"{state.diff.removed} line(s) removed and {state.diff.added} added" if state.diff else "the code was edited"
        )
        return WhyItWorked(
            what_was_wrong=(a.likely_cause if a else state.diagnosis) or state.diagnosis,
            what_changed=changed,
            why_it_worked=state.reasoning or state.diagnosis or "The corrected code ran successfully in the sandbox.",
            concepts=[a.concept_hint] if a and a.concept_hint else [],
            remember="Read the error message first: it names the exact line and the kind of mistake.",
        )

    # ------------------------------------------------------------------ helpers
    async def _ensure_error(self, ctx: AgentContext, mode: str) -> DebugResponse | None:
        """If the user gave no error text, reproduce it by running the code once."""
        state = ctx.state
        if state.error:
            return None
        ctx.emit({"type": "status", "stage": "reproducing", "message": "No error given. Running your code to reproduce it..."})
        run = await self.executor.run(state.code)
        matches = compare_output(run.stdout, state.expected_output)
        log_tool(ctx, "execute_python", "reproduce the error (not counted as an attempt)", ok=not run.success, by="orchestrator")
        if run.success and matches is not False:
            msg = "Your code ran without any error."
            if run.stdout.strip():
                msg += f"\n\nOutput:\n{run.stdout.strip()}"
            return self._response(state, mode, "no_error", msg)
        if run.success and matches is False:
            state.error = f"Wrong output.\nExpected:\n{state.expected_output}\nActual:\n{run.stdout}"
        else:
            state.error = (run.stderr or run.note or "The program failed without an error message.").strip()
        state.warnings.append("No error message was provided, so the code was run to reproduce it.")
        return None

    def _response(self, state: AgentState, mode: str, status: str, message: str) -> DebugResponse:
        explanation: Explanation | None = state.explanation
        fix: FixResult | None = None
        if mode == "fix" and state.current_fix is not None:
            fix = FixResult(
                diagnosis=state.diagnosis,
                fixed_code=state.current_fix,
                changes=state.changes,
                reasoning=state.reasoning,
                diff=state.diff,
                verified=state.fix_verified,
            )
        return DebugResponse(
            mode=mode,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            error_type=(state.analysis.error_type if state.analysis else ""),
            message=message,
            explanation=explanation,
            fix=fix,
            attempts=state.attempts,
            max_attempts=state.max_attempts,
            why_it_worked=state.why_it_worked,
            tool_trace=state.tool_trace,
            warnings=state.warnings,
            code=state.code,
            error=state.error,
            explanation_mode=state.explanation_mode,  # type: ignore[arg-type]
        )

    async def _finish(self, response: DebugResponse) -> DebugResponse:
        try:
            response.id = await self.history.save(response)
        except Exception:  # history is a convenience; never fail the request because of it
            log.exception("could not save history")
            response.warnings.append("This session could not be saved to history.")
        return response
