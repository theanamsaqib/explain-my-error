"""The agent loop: tool calling, observation, retry, guard rails and graceful failures.

The LLM is the scripted fake, so these tests check OUR logic (loop, budget, ground truth,
fallbacks) deterministically. They say nothing about the quality of a real model.
"""

from __future__ import annotations

import pytest

from app.errors import AppError
from app.models.schemas import DebugRequest
from tests.conftest import traceback_for
from tests.fake_llm import ScriptedLLM


def fix_req(bug: dict, error: str | None = None, **kw) -> DebugRequest:
    return DebugRequest(
        mode="fix", code=bug["code"], error=traceback_for(bug) if error is None else error,
        expected_output=bug["expected_output"], **kw,
    )


# --------------------------------------------------------------------------- happy path
async def test_first_attempt_success_runs_the_full_loop(make_service, bugs):
    svc = make_service()
    r = await svc.handle(fix_req(bugs["index_error_basic"]))

    assert r.status == "fixed" and r.fix and r.fix.verified
    assert len(r.attempts) == 1 and r.attempts[0].success
    assert "range(len(numbers)):" in r.fix.fixed_code
    assert r.fix.diff and r.fix.diff.added == 1 and r.fix.diff.removed == 1
    assert r.why_it_worked and r.why_it_worked.concepts
    tools = [t.tool for t in r.tool_trace]
    assert tools[0] == "analyze_code" and "execute_python" in tools and "generate_diff" in tools
    assert r.id is not None  # saved to history


async def test_retry_loop_observes_failure_then_fixes(make_service, bugs):
    """Demo 3: the first candidate fails, the agent observes the NEW error and tries again."""
    svc = make_service()
    r = await svc.handle(fix_req(bugs["chained_two_bugs"]))

    assert r.status == "fixed" and len(r.attempts) == 2
    first, second = r.attempts
    assert not first.success and "KeyError" in first.observation
    assert "KeyError: 'count'" in first.execution.stderr
    assert second.success and second.execution.stdout.strip() == "90.0"
    # the agent re-analysed the failure between the two attempts
    order = [(t.tool, t.by) for t in r.tool_trace]
    assert order.index(("analyze_code", "agent")) < len(order) - 1
    assert second.analyzed
    assert "len(marks[" in r.fix.fixed_code


async def test_events_stream_in_agent_order(make_service, bugs):
    events: list[dict] = []
    await make_service().handle(fix_req(bugs["chained_two_bugs"]), events.append)
    kinds = [(e["type"], e.get("attempt")) for e in events if e["type"].startswith("attempt")]
    assert kinds == [
        ("attempt_started", 1), ("attempt_running", 1), ("attempt_result", 1),
        ("attempt_started", 2), ("attempt_running", 2), ("attempt_result", 2),
    ]
    first_result = next(e for e in events if e["type"] == "attempt_result")
    assert first_result["data"]["success"] is False


# --------------------------------------------------------------------------- budget / ground truth
async def test_attempt_budget_is_enforced_even_if_the_llm_ignores_it(make_service, bugs):
    naive = bugs["chained_two_bugs"]["naive_fix"]
    llm = ScriptedLLM(attempts={"chained_two_bugs": [naive] * 6}, ignore_budget=True)
    r = await make_service(llm).handle(fix_req(bugs["chained_two_bugs"]))

    assert r.status == "failed"
    assert len(r.attempts) == 3  # hard stop at max_attempts
    assert all(not a.success for a in r.attempts)
    assert "Could not verify a fix after 3 attempts" in r.message
    assert r.why_it_worked is None
    assert r.fix and not r.fix.verified  # best candidate is still shown, clearly unverified
    refused = [t for t in r.tool_trace if "budget exhausted" in t.summary]
    assert refused  # the 4th execute_python call was refused by the tool


async def test_success_is_decided_by_the_sandbox_not_by_the_llm(make_service, bugs):
    """The model claims success, but the program's output does not match the expected output."""
    bug = bugs["wrong_conditional_adult"]
    wrong = bug["code"]  # still buggy: runs fine, prints False/True
    llm = ScriptedLLM(attempts={bug["id"]: [wrong, wrong, wrong]}, ignore_budget=True)
    r = await make_service(llm).handle(fix_req(bug, error="Wrong output.\nExpected: True True"))

    assert r.status == "failed"
    assert r.attempts[0].execution.exit_code == 0  # ran cleanly...
    assert not r.attempts[0].success  # ...but is NOT a success: output mismatch
    assert "did not match" in r.attempts[0].observation


async def test_unfixable_timeout_is_reported_not_hung(make_service, bugs):
    bug = bugs["infinite_loop_no_increment"]
    llm = ScriptedLLM(attempts={bug["id"]: [bug["code"]] * 3}, ignore_budget=True)
    r = await make_service(llm).handle(fix_req(bug, error="Execution timed out after 2s (possible infinite loop)."))
    assert r.status == "failed"
    assert all(a.execution.timed_out for a in r.attempts)


# --------------------------------------------------------------------------- guard rails / fallbacks
async def test_agent_that_skips_the_tool_gets_its_code_executed_by_the_system(make_service, bugs):
    r = await make_service(ScriptedLLM(no_tools=True)).handle(fix_req(bugs["index_error_basic"]))
    assert r.status == "fixed"
    assert r.attempts[0].source == "orchestrator"
    assert any("without testing it" in w for w in r.warnings)


async def test_malformed_final_answer_does_not_break_the_result(make_service, bugs):
    r = await make_service(ScriptedLLM(malformed_final=True)).handle(fix_req(bugs["index_error_basic"]))
    assert r.status == "fixed" and r.fix and r.fix.fixed_code
    assert any("malformed" in w for w in r.warnings)


async def test_unknown_code_returns_failed_not_a_crash(make_service):
    req = DebugRequest(mode="fix", code="print(undefined_thing)", error="NameError: name 'undefined_thing' is not defined")
    r = await make_service().handle(req)
    assert r.status == "failed" and "did not produce a fix" in r.message


async def test_fix_without_llm_key_gives_clear_error(make_service, bugs):
    with pytest.raises(AppError) as exc:
        await make_service(configured=False).handle(fix_req(bugs["index_error_basic"]))
    assert exc.value.code == "llm_not_configured"


async def test_provider_auth_failure_is_translated(make_service, bugs):
    with pytest.raises(AppError) as exc:
        await make_service(ScriptedLLM(fail="auth")).handle(fix_req(bugs["index_error_basic"]))
    assert exc.value.code == "llm_auth" and "API key" in exc.value.message
    assert "Traceback" not in exc.value.message


async def test_provider_unreachable_is_translated(make_service, bugs):
    with pytest.raises(AppError) as exc:
        await make_service(ScriptedLLM(fail="connect")).handle(fix_req(bugs["index_error_basic"]))
    assert exc.value.code == "llm_unreachable"


async def test_unsupported_language(make_service, bugs):
    req = DebugRequest(mode="fix", code="console.log(1)", error="x", language="javascript")
    with pytest.raises(AppError) as exc:
        await make_service().handle(req)
    assert exc.value.code == "unsupported_language"


# --------------------------------------------------------------------------- explain mode
async def test_explain_mode_uses_analysis_and_returns_structured_explanation(make_service, bugs):
    llm = ScriptedLLM()
    r = await make_service(llm).handle(
        DebugRequest(mode="explain", code=bugs["index_error_basic"]["code"], error=traceback_for(bugs["index_error_basic"]))
    )
    assert r.status == "explained" and r.explanation and r.explanation.source == "llm"
    assert r.explanation.error_type == "IndexError"
    assert 3 in r.explanation.problematic_lines  # root cause: the range() line
    assert "range(len(numbers) + 1)" in r.explanation.problematic_code
    assert r.fix is None and not r.attempts  # explaining never executes anything
    # the LLM received the static analysis produced by the analyze_code tool
    assert "STATIC ANALYSIS" in llm.calls[-1]["messages"][-1]["content"]


@pytest.mark.parametrize(
    "mode,marker",
    [("eli5", "EXPLAIN LIKE I'M 5"), ("cs_student", "CS STUDENT"), ("interview", "INTERVIEW"), ("technical", "STACK OVERFLOW")],
)
async def test_each_explanation_style_changes_the_prompt(make_service, bugs, mode, marker):
    llm = ScriptedLLM()
    await make_service(llm).handle(
        DebugRequest(mode="explain", code=bugs["index_error_basic"]["code"], error=traceback_for(bugs["index_error_basic"]), explanation_mode=mode)
    )
    assert marker in llm.calls[-1]["messages"][0]["content"]


async def test_explain_falls_back_to_static_analysis_when_llm_fails(make_service, bugs):
    r = await make_service(ScriptedLLM(fail="auth")).handle(
        DebugRequest(mode="explain", code=bugs["index_error_basic"]["code"], error=traceback_for(bugs["index_error_basic"]))
    )
    assert r.status == "explained" and r.explanation.source == "static"
    assert r.explanation.error_type == "IndexError"
    assert any("static analysis" in w for w in r.warnings)


async def test_explain_without_any_llm_configured(make_service, bugs):
    r = await make_service(configured=False).handle(
        DebugRequest(mode="explain", code=bugs["index_error_basic"]["code"], error=traceback_for(bugs["index_error_basic"]))
    )
    assert r.explanation.source == "static" and any("OPENAI_API_KEY" in w for w in r.warnings)


# --------------------------------------------------------------------------- missing / odd input
async def test_missing_error_is_reproduced_by_running_the_code(make_service, bugs):
    r = await make_service().handle(DebugRequest(mode="explain", code=bugs["index_error_basic"]["code"], error=""))
    assert "IndexError" in r.error
    assert any("reproduce" in w for w in r.warnings)
    assert r.explanation.error_type == "IndexError"


async def test_code_that_already_works_reports_no_error(make_service):
    r = await make_service().handle(DebugRequest(mode="fix", code="print('all good')", error=""))
    assert r.status == "no_error" and "all good" in r.message and not r.attempts


def test_blank_code_is_rejected_by_validation():
    with pytest.raises(ValueError):
        DebugRequest(mode="fix", code="   \n ", error="x")


async def test_history_roundtrip(make_service, bugs):
    svc = make_service()
    r = await svc.handle(fix_req(bugs["index_error_basic"]))
    items = await svc.history.list()
    assert items[0].id == r.id and items[0].error_type == "IndexError" and items[0].status == "fixed"
    stored = await svc.history.get(r.id)
    assert stored and stored.fix.fixed_code == r.fix.fixed_code and len(stored.attempts) == 1
    assert await svc.history.get(99999) is None
