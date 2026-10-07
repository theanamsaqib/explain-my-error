"""The execute_python tool: behaviour and sandbox guard rails."""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.tools.code_executor import SubprocessExecutor, compare_output


async def test_successful_run(executor):
    r = await executor.run("print('hello')")
    assert r.success and r.stdout == "hello\n" and r.exit_code == 0 and not r.timed_out
    assert r.stderr == ""


async def test_exception_is_reported_with_clean_traceback(executor):
    r = await executor.run("numbers = [1, 2, 3]\nfor i in range(4):\n    print(numbers[i])\n")
    assert not r.success and r.exit_code == 1
    assert "IndexError: list index out of range" in r.stderr
    assert 'File "main.py", line 3' in r.stderr
    assert "runner.py" not in r.stderr  # sandbox wrapper frames are hidden
    assert r.stdout == "1\n2\n3\n"  # output before the crash is kept


async def test_syntax_error_has_no_wrapper_frames(executor):
    r = await executor.run("def f(:\n    pass\n")
    assert not r.success
    assert "SyntaxError" in r.stderr and "runner.py" not in r.stderr


async def test_timeout_stops_infinite_loop(settings):
    ex = SubprocessExecutor(Settings(**{**settings.__dict__, "execution_timeout": 1.0}))
    r = await ex.run("while True:\n    pass\n")
    assert r.timed_out and not r.success
    assert "timed out" in r.note
    assert r.duration_ms < 4000


async def test_output_flood_is_capped(settings):
    ex = SubprocessExecutor(Settings(**{**settings.__dict__, "max_output_size": 1000}))
    r = await ex.run("while True:\n    print('x' * 500)\n")
    assert not r.success and r.output_truncated
    assert len(r.stdout) < 1200  # capped (plus the truncation notice)


async def test_secrets_are_not_visible(executor, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret")
    r = await executor.run("import os\nprint(sorted(os.environ))\n")
    assert r.success
    assert "OPENAI" not in r.stdout and "sk-super-secret" not in r.stdout


async def test_network_is_blocked(executor):
    r = await executor.run("import socket\ns = socket.socket()\ns.connect(('example.com', 80))\n")
    assert not r.success
    assert "Network access is disabled" in r.stderr


async def test_stdin_is_closed_so_input_cannot_hang(executor):
    r = await executor.run("input()")
    assert not r.success and "EOFError" in r.stderr


async def test_third_party_imports_are_unavailable(executor):
    r = await executor.run("import fastapi")
    assert not r.success and "ModuleNotFoundError" in r.stderr


async def test_empty_output_is_flagged(executor):
    r = await executor.run("x = 1")
    assert r.success and "printed nothing" in r.note


async def test_sys_exit_code_is_preserved(executor):
    r = await executor.run("import sys\nsys.exit(3)")
    assert r.exit_code == 3 and not r.success


async def test_temp_dirs_are_cleaned_up(executor):
    import tempfile
    from pathlib import Path

    before = set(Path(tempfile.gettempdir()).glob("eme_run_*"))
    await executor.run("print(1)")
    after = set(Path(tempfile.gettempdir()).glob("eme_run_*"))
    assert after <= before


@pytest.mark.parametrize(
    "actual,expected,result",
    [("1\n2\n", "1\n2", True), ("1 \n2", "1\n2", True), ("1\n3", "1\n2", False), ("anything", None, None), ("anything", "  ", None)],
)
def test_compare_output(actual, expected, result):
    assert compare_output(actual, expected) is result
