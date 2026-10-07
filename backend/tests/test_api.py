"""HTTP contract tests (FastAPI TestClient) with the scripted fake LLM behind the service."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import traceback_for


@pytest.fixture
def client(settings, make_service):
    app = create_app(settings, service=make_service())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def body(bug: dict, mode: str = "fix", **extra) -> dict:
    return {"mode": mode, "code": bug["code"], "error": traceback_for(bug), "explanation_mode": "cs_student",
            "expected_output": bug["expected_output"], **extra}


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["llm_configured"] is True and data["max_attempts"] == 3
    assert data["execution_backend"] == "subprocess"


def test_debug_explain_contract(client, bugs):
    r = client.post("/api/debug", json=body(bugs["index_error_basic"], "explain"))
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "explain" and d["status"] == "explained"
    assert set(d["explanation"]) >= {"error_type", "summary", "explanation", "concept", "problematic_lines", "problematic_code", "source"}
    assert d["fix"] is None and d["attempts"] == []


def test_debug_fix_contract(client, bugs):
    r = client.post("/api/debug", json=body(bugs["chained_two_bugs"]))
    d = r.json()
    assert r.status_code == 200 and d["status"] == "fixed"
    assert len(d["attempts"]) == 2 and d["attempts"][0]["success"] is False
    assert set(d["attempts"][0]) >= {"number", "analyzed", "rationale", "code", "execution", "success", "observation", "source"}
    assert set(d["attempts"][0]["execution"]) >= {"success", "stdout", "stderr", "exit_code", "timed_out"}
    assert d["fix"]["verified"] is True
    assert set(d["fix"]["diff"]) >= {"unified_diff", "lines", "added", "removed", "changed"}
    assert set(d["why_it_worked"]) >= {"what_was_wrong", "what_changed", "why_it_worked", "concepts", "remember"}
    assert d["max_attempts"] == 3 and d["id"]


def test_stream_emits_attempt_events_then_result(client, bugs):
    r = client.post("/api/debug/stream", json=body(bugs["chained_two_bugs"]))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [n for n, _ in events]
    assert names[-1] == "result" and "attempt_result" in names
    results = [d for n, d in events if n == "attempt_result"]
    assert results[0]["data"]["success"] is False and results[1]["data"]["success"] is True
    final = events[-1][1]["response"]
    assert final["status"] == "fixed" and len(final["attempts"]) == 2


def test_stream_reports_errors_as_an_event(settings, make_service, bugs):
    app = create_app(settings, service=make_service(configured=False))
    with TestClient(app) as c:
        events = parse_sse(c.post("/api/debug/stream", json=body(bugs["index_error_basic"])).text)
    name, data = events[-1]
    assert name == "error" and data["error"]["code"] == "llm_not_configured"


def test_validation_errors_are_friendly(client):
    r = client.post("/api/debug", json={"mode": "fix", "code": "   ", "error": "x"})
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "validation_error", "message": "Please paste some code first."}}
    r = client.post("/api/debug", json={"mode": "dance", "code": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_unsupported_language_is_a_400(client):
    r = client.post("/api/debug", json={"mode": "explain", "code": "puts 1", "error": "x", "language": "ruby"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_language"


def test_history_endpoints(client, bugs):
    assert client.get("/api/debug/history").json() == []
    first = client.post("/api/debug", json=body(bugs["index_error_basic"], "explain")).json()
    client.post("/api/debug", json=body(bugs["index_error_basic"]))
    items = client.get("/api/debug/history").json()
    assert [i["mode"] for i in items] == ["fix", "explain"] and items[0]["error_type"] == "IndexError"
    one = client.get(f"/api/debug/history/{first['id']}")
    assert one.status_code == 200 and one.json()["explanation"]["error_type"] == "IndexError"
    missing = client.get("/api/debug/history/9999")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_unexpected_crash_never_leaks_a_stack_trace(settings, make_service, bugs, monkeypatch):
    svc = make_service()

    async def boom(*a, **k):
        raise RuntimeError("secret internal detail /home/user/app.py line 42")

    monkeypatch.setattr(svc, "handle", boom)
    with TestClient(create_app(settings, service=svc), raise_server_exceptions=False) as c:
        r = c.post("/api/debug", json=body(bugs["index_error_basic"]))
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Something went wrong on the server."}}
    assert "secret" not in r.text and "Traceback" not in r.text
