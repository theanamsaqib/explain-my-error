"""Validates the fixtures themselves and the two deterministic tools (analyzer, diff)."""

from __future__ import annotations

import pytest

from app.tools.code_analyzer import analyze_code, parse_error
from app.tools.diff_generator import generate_diff
from evaluate import derive_error
from tests.fake_llm import load_bugs

BUGS = load_bugs()


def test_there_are_at_least_15_bugs_with_unique_ids():
    assert len(BUGS) >= 15
    assert len({b["id"] for b in BUGS}) == len(BUGS)


@pytest.mark.parametrize("bug", BUGS, ids=[b["id"] for b in BUGS])
async def test_buggy_code_really_fails_and_reference_fix_really_works(bug, executor):
    error = await derive_error(executor, bug)  # raises if the "bug" does not actually misbehave
    assert error.strip()

    fixed = await executor.run(bug["reference_fix"])
    assert fixed.success, fixed.stderr
    assert fixed.stdout.strip() == bug["expected_output"].strip()

    if bug.get("naive_fix"):
        naive = await executor.run(bug["naive_fix"])
        assert not naive.success  # the "plausible but incomplete" fix must still fail


@pytest.mark.parametrize(
    "bug", [b for b in BUGS if b["error_kind"] == "exception"], ids=[b["id"] for b in BUGS if b["error_kind"] == "exception"]
)
async def test_static_analyzer_identifies_every_exception_fixture(bug, executor):
    error = await derive_error(executor, bug)
    analysis = analyze_code(bug["code"], error)
    assert analysis.error_type.lower() in bug["accepted_types"] or analysis.error_type == bug["expected_error_type"]
    assert analysis.line_number is not None or analysis.error_type == "ImportError"
    assert analysis.suspicious_lines


def test_analyzer_flags_the_off_by_one_range():
    code = "numbers = [1, 2, 3]\n\nfor i in range(len(numbers) + 1):\n    print(numbers[i])\n"
    err = 'Traceback (most recent call last):\n  File "main.py", line 4, in <module>\nIndexError: list index out of range'
    a = analyze_code(code, err)
    assert a.error_type == "IndexError" and a.line_number == 4
    assert any(s.line == 3 and "range" in s.code for s in a.suspicious_lines)
    assert a.concept_hint.startswith("Zero-based")


def test_analyzer_suggests_close_name_for_typos():
    a = analyze_code("total = 5\nprint(totl)\n", "NameError: name 'totl' is not defined")
    assert "total" in a.likely_cause


def test_analyzer_handles_garbage_input_gracefully():
    a = analyze_code("x = (", "something is wrong")
    assert a.error_type == "SyntaxError" and not a.syntax_ok
    b = analyze_code("print(1)", "")
    assert b.error_type == "Unknown"


def test_parse_error_variants():
    assert parse_error("builtins.ValueError: bad")[0] == "ValueError"
    assert parse_error("Execution timed out after 5s")[0] == "TimeoutError"
    assert parse_error("Wrong output.\nExpected:\n1")[0] == "LogicError"


def test_diff_generator_marks_added_and_removed_lines():
    d = generate_diff("a = 1\nfor i in range(n + 1):\n    pass\n", "a = 1\nfor i in range(n):\n    pass\n")
    assert d.changed and d.added == 1 and d.removed == 1
    kinds = [(ln.type, ln.text) for ln in d.lines if ln.type != "context"]
    assert kinds == [("remove", "for i in range(n + 1):"), ("add", "for i in range(n):")]
    assert "-for i in range(n + 1):" in d.unified_diff


def test_diff_of_identical_code_is_empty():
    d = generate_diff("x = 1\n", "x = 1\n")
    assert not d.changed and d.lines == []
