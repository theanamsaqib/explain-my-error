"""A scripted, deterministic stand-in for an OpenAI-compatible Chat Completions API.

NOT a real model. It exists so the agent loop (tool calls, retries, guard rails) can be tested
without an API key and so the app can be demoed offline. It only "knows" the bugs in
fixtures/bugs.json: it recognises the user's code, then replies with tool calls and canned JSON
built from the fixture (naive_fix -> reference_fix for the chained-bug scenario).
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bugs.json"
_NUMBERED = re.compile(r"^\s*\d+ \| ?", re.M)


def load_bugs() -> list[dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _completion(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    return {
        "id": "chatcmpl-scripted",
        "object": "chat.completion",
        "created": 0,
        "model": "scripted-demo-llm",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if tool_calls else "stop",
                "message": {"role": "assistant", "content": content, "tool_calls": tool_calls},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class ScriptedLLM:
    def __init__(
        self,
        bugs: list[dict] | None = None,
        *,
        attempts: dict[str, list[str]] | None = None,  # bug id -> codes to try, in order
        ignore_budget: bool = False,  # keep calling execute_python after the budget is spent
        no_tools: bool = False,  # answer with code but never call execute_python
        malformed_final: bool = False,  # final fixer answer is not JSON
        fail: str | None = None,  # "auth" | "connect" -> simulate provider failure
        label: bool = False,  # prefix text so a UI viewer knows this is not a real model
    ) -> None:
        self.bugs = bugs or load_bugs()
        self.attempts_override = attempts or {}
        self.ignore_budget = ignore_budget
        self.no_tools = no_tools
        self.malformed_final = malformed_final
        self.fail = fail
        self.label = label
        self.calls: list[dict] = []

    # ------------------------------------------------------------------ transport
    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.fail == "connect":
            raise httpx.ConnectError("scripted connection failure", request=request)
        if self.fail == "auth":
            return httpx.Response(401, json={"error": {"message": "Incorrect API key", "type": "invalid_request_error"}})
        return httpx.Response(200, json=self.respond(json.loads(request.content)))

    def client(self) -> AsyncOpenAI:
        transport = httpx.MockTransport(self.handle)
        return AsyncOpenAI(
            api_key="test-key",
            base_url="http://scripted-llm.test/v1",
            http_client=httpx.AsyncClient(transport=transport),
            max_retries=0,
        )

    # ------------------------------------------------------------------ helpers
    def _bug_for(self, user_text: str) -> dict | None:
        plain = _NUMBERED.sub("", user_text)
        for bug in self.bugs:
            if bug["code"].strip() in plain:
                return bug
        return None

    def _codes(self, bug: dict) -> list[str]:
        if bug["id"] in self.attempts_override:
            return self.attempts_override[bug["id"]]
        return ([bug["naive_fix"]] if bug.get("naive_fix") else []) + [bug["reference_fix"]]

    def _tag(self, text: str) -> str:
        return f"[scripted demo LLM] {text}" if self.label else text

    @staticmethod
    def _tool_call(msgs: list[dict], name: str, args: dict) -> dict:
        call = {"id": f"call_{len(msgs)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        return _completion(tool_calls=[call])

    # ------------------------------------------------------------------ main entry
    def respond(self, body: dict) -> dict:
        self.calls.append(body)
        msgs = body["messages"]
        system = next((_text(m["content"]) for m in msgs if m["role"] == "system"), "")
        user = next((_text(m["content"]) for m in msgs if m["role"] == "user"), "")
        tool_names = {t["function"]["name"] for t in body.get("tools") or []}
        bug = self._bug_for(user)

        if "execute_python" in tool_names:
            return self._fixer(msgs, bug)
        if "Why Did My Fix Work" in system:
            return _completion(json.dumps(self._why(bug)))
        return _completion(json.dumps(self._explain(bug)))

    # ------------------------------------------------------------------ explain / why
    def _changed_lines(self, bug: dict) -> list[int]:
        a, b = bug["code"].splitlines(), bug["reference_fix"].splitlines()
        out: list[int] = []
        for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, a, b).get_opcodes():
            if tag != "equal":
                out.extend(range(i1 + 1, max(i2, i1 + 1) + 1 if tag == "insert" else i2 + 1))
        return [n for n in out if 1 <= n <= len(a)][:3] or [1]

    def _explain(self, bug: dict | None) -> dict:
        if bug is None:
            return {"error_type": "Unknown", "summary": "The scripted demo model does not know this code.",
                    "explanation": "Add your own OPENAI_API_KEY to get real explanations.", "concept": "n/a",
                    "problematic_lines": [], "example": None}
        return {
            "error_type": bug["expected_error_type"],
            "summary": self._tag(bug["title"] + "."),
            "explanation": f"**What went wrong:** {bug['title']}.\n\n**Where:** see the highlighted line(s).\n\n"
                           f"**Why:** this is a classic {bug['category']} mistake.",
            "concept": bug["category"],
            "problematic_lines": self._changed_lines(bug),
            "example": None,
        }

    def _why(self, bug: dict | None) -> dict:
        title = bug["title"] if bug else "the bug"
        return {
            "what_was_wrong": self._tag(f"{title}."),
            "what_changed": "The offending expression was corrected (see the diff).",
            "why_it_worked": "After the change every value the program uses is valid, so it runs to completion.",
            "concepts": [bug["category"]] if bug else [],
            "remember": "Read the error message first: it points to the line and the kind of mistake.",
        }

    # ------------------------------------------------------------------ fixer agent
    def _final(self, bug: dict | None, code: str, success: bool) -> dict:
        if self.malformed_final:
            return _completion("Sure! I fixed it, trust me.")
        return _completion(
            json.dumps(
                {
                    "diagnosis": self._tag(bug["title"] if bug else "unknown"),
                    "fixed_code": code,
                    "changes": ["Corrected the faulty expression"] if success else [],
                    "reasoning": "Verified by execution." if success else "Could not get the program to pass.",
                }
            )
        )

    def _fixer(self, msgs: list[dict], bug: dict | None) -> dict:
        if bug is None:
            return self._final(None, "", False)
        codes = self._codes(bug)
        if self.no_tools:
            return self._final(bug, codes[-1], True)

        parsed: list[dict] = []
        for m in msgs:
            if m["role"] == "tool":
                try:
                    parsed.append(json.loads(_text(m["content"])))
                except json.JSONDecodeError:
                    parsed.append({})
        last_code = ""
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                if tc["function"]["name"] == "execute_python":
                    last_code = json.loads(tc["function"]["arguments"]).get("code", "")

        n_exec = sum(1 for d in parsed if "attempts_remaining" in d)
        if not parsed:
            return self._tool_call(msgs, "execute_python", {"code": codes[0], "rationale": "First candidate fix."})

        last = parsed[-1]
        if "error_type" in last:  # analysis just returned -> try the next candidate
            code = codes[min(n_exec, len(codes) - 1)]
            return self._tool_call(msgs, "execute_python", {"code": code, "rationale": "Improved fix after analysing the new failure."})
        if "unified_diff" in last:
            return self._final(bug, last_code, True)
        if last.get("error") == "attempt_limit_reached":
            return self._final(bug, last_code, False)
        if last.get("success"):
            return self._tool_call(msgs, "generate_diff", {"original": bug["code"], "fixed": last_code})
        if last.get("attempts_remaining", 0) > 0 or self.ignore_budget:
            return self._tool_call(msgs, "analyze_code", {"code": last_code, "error": last.get("stderr") or last.get("note") or ""})
        return self._final(bug, last_code, False)
