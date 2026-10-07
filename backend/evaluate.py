"""Evaluation harness: runs the agent against every bug in tests/fixtures/bugs.json.

    python evaluate.py                      # all bugs, needs a real LLM key in .env
    python evaluate.py --ids index_error_basic,chained_two_bugs
    python evaluate.py --style interview --out my_run.json

Nothing here is hard-coded or invented: every number is computed from real executions.

How a case is run
  1. The buggy code is executed in the sandbox to obtain the REAL error text (or a "wrong output"
     / "timed out" description for logic bugs and infinite loops).
  2. mode=explain  -> was the error type identified? how complete is the explanation?
  3. mode=fix      -> did the agent produce a fix whose stdout matches the fixture's expected
     output, and how many attempts did it take?

Metrics
  - Error identification accuracy: predicted error_type matches one of the accepted names.
  - First-attempt fix success rate: attempt 1 passed (exit 0 AND expected output matched).
  - Overall fix success rate: final fix verified within the attempt budget.
  - Average attempts per successful fix.
  - Explanation completeness: STRUCTURAL score only (are all required parts present and non-trivial);
    it does not judge whether the explanation is correct or well written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from app.errors import AppError
from app.models.schemas import DebugRequest, DebugResponse
from app.tools.code_executor import Executor, compare_output

FIXTURES = Path(__file__).parent / "tests" / "fixtures" / "bugs.json"


def load_bugs() -> list[dict[str, Any]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


async def derive_error(executor: Executor, bug: dict) -> str:
    """Run the buggy code and describe how it misbehaves. Raises if it does not misbehave."""
    run = await executor.run(bug["code"])
    if run.timed_out or "too much output" in run.note:
        return run.note
    if not run.success:
        return run.stderr.strip() or "The program failed without an error message."
    if compare_output(run.stdout, bug["expected_output"]) is False:
        return f"Wrong output.\nExpected:\n{bug['expected_output']}\nActual:\n{run.stdout.strip()}"
    raise ValueError(f"fixture {bug['id']} does not fail: it is not a bug")


def explanation_completeness(resp: DebugResponse | None) -> float:
    e = resp.explanation if resp else None
    if e is None:
        return 0.0
    checks = [
        bool(e.error_type.strip()),
        len(e.summary.strip()) >= 15,
        len(e.explanation.strip()) >= 60,
        bool(e.concept.strip()),
        bool(e.problematic_lines),
    ]
    return sum(checks) / len(checks)


def why_completeness(resp: DebugResponse | None) -> float | None:
    w = resp.why_it_worked if resp else None
    if w is None:
        return None
    checks = [
        len(w.what_was_wrong.strip()) >= 10,
        len(w.what_changed.strip()) >= 10,
        len(w.why_it_worked.strip()) >= 10,
        bool(w.concepts),
        len(w.remember.strip()) >= 10,
    ]
    return sum(checks) / len(checks)


async def evaluate_case(service, executor: Executor, bug: dict, style: str) -> dict[str, Any]:
    started = time.monotonic()
    row: dict[str, Any] = {
        "id": bug["id"],
        "category": bug["category"],
        "expected_error_type": bug["expected_error_type"],
        "predicted_error_type": None,
        "identified": False,
        "explanation_source": None,
        "explanation_completeness": 0.0,
        "fix_status": None,
        "attempts": 0,
        "first_attempt_success": False,
        "fixed": False,
        "why_completeness": None,
        "errors": [],
    }
    error = await derive_error(executor, bug)

    try:
        explained = await service.handle(
            DebugRequest(mode="explain", code=bug["code"], error=error, explanation_mode=style, expected_output=bug["expected_output"])
        )
        predicted = (explained.explanation.error_type if explained.explanation else "").strip()
        row["predicted_error_type"] = predicted
        row["identified"] = any(alias in predicted.lower() for alias in bug["accepted_types"])
        row["explanation_source"] = explained.explanation.source if explained.explanation else None
        row["explanation_completeness"] = explanation_completeness(explained)
    except AppError as exc:
        row["errors"].append(f"explain: {exc.message}")

    try:
        fixed = await service.handle(
            DebugRequest(mode="fix", code=bug["code"], error=error, explanation_mode=style, expected_output=bug["expected_output"])
        )
        row["fix_status"] = fixed.status
        row["attempts"] = len(fixed.attempts)
        row["first_attempt_success"] = bool(fixed.attempts and fixed.attempts[0].success)
        row["fixed"] = fixed.status == "fixed" and bool(fixed.fix and fixed.fix.verified)
        row["why_completeness"] = why_completeness(fixed)
    except AppError as exc:
        row["fix_status"] = "error"
        row["errors"].append(f"fix: {exc.message}")

    row["seconds"] = round(time.monotonic() - started, 1)
    return row


def summarize(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    fixed = [r for r in rows if r["fixed"]]
    whys = [r["why_completeness"] for r in rows if r["why_completeness"] is not None]
    by_cat: dict[str, dict] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"cases": 0, "identified": 0, "fixed": 0})
        c["cases"] += 1
        c["identified"] += int(r["identified"])
        c["fixed"] += int(r["fixed"])
    return {
        "cases": n,
        "error_identification_accuracy": sum(r["identified"] for r in rows) / n if n else None,
        "first_attempt_fix_rate": sum(r["first_attempt_success"] for r in rows) / n if n else None,
        "overall_fix_rate": len(fixed) / n if n else None,
        "avg_attempts_per_successful_fix": mean(r["attempts"] for r in fixed) if fixed else None,
        "explanation_completeness": mean(r["explanation_completeness"] for r in rows) if n else None,
        "why_it_worked_completeness": mean(whys) if whys else None,
        "static_fallback_explanations": sum(1 for r in rows if r["explanation_source"] == "static"),
        "cases_with_errors": [r["id"] for r in rows if r["errors"]],
        "by_category": by_cat,
    }


async def evaluate(
    service, executor: Executor, bugs: list[dict], style: str = "cs_student", progress: Callable[[dict], None] | None = None
) -> tuple[list[dict], dict]:
    rows = []
    for bug in bugs:
        row = await evaluate_case(service, executor, bug, style)
        rows.append(row)
        if progress:
            progress(row)
    return rows, summarize(rows)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_markdown(summary: dict, rows: list[dict], meta: dict) -> str:
    avg = summary["avg_attempts_per_successful_fix"]
    out = [
        "# Evaluation results",
        "",
        f"Model: `{meta['model']}` | style: `{meta['style']}` | max attempts: {meta['max_attempts']} | "
        f"run at {meta['timestamp']} | cases: {summary['cases']}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Error identification accuracy | {_pct(summary['error_identification_accuracy'])} |",
        f"| First-attempt fix success rate | {_pct(summary['first_attempt_fix_rate'])} |",
        f"| Overall fix success rate | {_pct(summary['overall_fix_rate'])} |",
        f"| Average attempts per successful fix | {'n/a' if avg is None else f'{avg:.2f}'} |",
        f"| Explanation completeness (structural) | {_pct(summary['explanation_completeness'])} |",
        f"| 'Why did my fix work?' completeness (structural) | {_pct(summary['why_it_worked_completeness'])} |",
        "",
        "| Case | Expected | Predicted | Fixed | Attempts | 1st try |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['id']} | {r['expected_error_type']} | {r['predicted_error_type'] or '-'} "
            f"| {'yes' if r['fixed'] else 'NO'} | {r['attempts']} | {'yes' if r['first_attempt_success'] else 'no'} |"
        )
    if summary["static_fallback_explanations"]:
        out += ["", f"Note: {summary['static_fallback_explanations']} explanation(s) fell back to static analysis because the LLM call failed."]
    if summary["cases_with_errors"]:
        out += ["", f"Cases with API errors: {', '.join(summary['cases_with_errors'])}"]
    return "\n".join(out) + "\n"


async def _main(args: argparse.Namespace) -> int:
    from app.agent.agent import build_llm_client
    from app.config import load_settings
    from app.services.debugger import DebugService
    from app.services.history import HistoryStore
    from app.tools.code_executor import build_executor

    settings = load_settings()
    if not settings.llm_configured:
        print("OPENAI_API_KEY is not set. Put it in backend/.env (see .env.example). The evaluation needs a real LLM.")
        return 2

    bugs = load_bugs()
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        bugs = [b for b in bugs if b["id"] in wanted]
    if args.limit:
        bugs = bugs[: args.limit]
    if not bugs:
        print("No matching bugs.")
        return 2

    executor = build_executor(settings)
    history = HistoryStore(Path(tempfile.mkdtemp(prefix="eme_eval_")) / "eval.db")  # keep real history clean
    service = DebugService(settings, executor, history, build_llm_client(settings))

    def progress(r: dict) -> None:
        mark = "OK " if r["fixed"] else "FAIL"
        print(f"[{mark}] {r['id']:<32} predicted={r['predicted_error_type'] or '-':<20} attempts={r['attempts']} ({r['seconds']}s)")

    print(f"Evaluating {len(bugs)} bugs with model {settings.openai_model} ...\n")
    rows, summary = await evaluate(service, executor, bugs, args.style, progress)

    meta = {
        "model": settings.openai_model,
        "base_url": settings.openai_base_url or "https://api.openai.com/v1",
        "style": args.style,
        "max_attempts": settings.max_attempts,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    report = render_markdown(summary, rows, meta)
    print("\n" + report)

    out = Path(args.out)
    out.write_text(json.dumps({"meta": meta, "summary": summary, "cases": rows}, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(report, encoding="utf-8")
    print(f"Saved {out} and {out.with_suffix('.md')}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the debugging agent on the fixture bugs.")
    parser.add_argument("--ids", help="comma-separated fixture ids to run")
    parser.add_argument("--limit", type=int, help="only run the first N bugs")
    parser.add_argument("--style", default="cs_student", choices=["eli5", "cs_student", "interview", "technical"])
    parser.add_argument("--out", default="evaluation_results.json")
    sys.exit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
