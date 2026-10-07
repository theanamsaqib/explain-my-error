"""Plumbing test for evaluate.py: checks the metric arithmetic, NOT the quality of any real model.

The scripted LLM is deterministic, so we know exactly what the right metrics are:
index_error_basic is fixed on attempt 1, chained_two_bugs needs 2 attempts.
"""

from __future__ import annotations

from evaluate import evaluate, render_markdown
from tests.fake_llm import load_bugs


async def test_metrics_are_computed_from_real_runs(make_service, executor):
    wanted = {"index_error_basic", "chained_two_bugs", "infinite_loop_no_increment"}
    bugs = [b for b in load_bugs() if b["id"] in wanted]
    rows, summary = await evaluate(make_service(), executor, bugs)

    by_id = {r["id"]: r for r in rows}
    assert by_id["index_error_basic"]["attempts"] == 1 and by_id["index_error_basic"]["first_attempt_success"]
    assert by_id["chained_two_bugs"]["attempts"] == 2 and not by_id["chained_two_bugs"]["first_attempt_success"]
    assert by_id["infinite_loop_no_increment"]["identified"]  # "TimeoutError" matches the accepted aliases

    assert summary["cases"] == 3
    assert summary["overall_fix_rate"] == 1.0
    assert abs(summary["first_attempt_fix_rate"] - 2 / 3) < 1e-9
    assert abs(summary["avg_attempts_per_successful_fix"] - (1 + 2 + 1) / 3) < 1e-9
    assert summary["explanation_completeness"] == 1.0
    assert summary["why_it_worked_completeness"] == 1.0

    report = render_markdown(summary, rows, {"model": "scripted", "style": "cs_student", "max_attempts": 3, "timestamp": "t"})
    assert "Overall fix success rate | 100.0%" in report


async def test_evaluation_counts_a_failure_as_a_failure(make_service, executor):
    from tests.fake_llm import ScriptedLLM

    bug = next(b for b in load_bugs() if b["id"] == "missing_return")
    llm = ScriptedLLM(attempts={bug["id"]: [bug["code"]] * 3}, ignore_budget=True)
    rows, summary = await evaluate(make_service(llm), executor, [bug])
    assert rows[0]["fixed"] is False and rows[0]["attempts"] == 3
    assert summary["overall_fix_rate"] == 0.0 and summary["avg_attempts_per_successful_fix"] is None
