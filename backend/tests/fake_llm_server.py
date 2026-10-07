"""Run the scripted fake LLM as a local OpenAI-compatible server (offline demo / UI testing).

    uvicorn tests.fake_llm_server:app --port 9999

Then in .env:  OPENAI_API_KEY=anything   OPENAI_BASE_URL=http://localhost:9999/v1

It is NOT an AI. It only recognises the bugs in tests/fixtures/bugs.json (use the example
buttons in the UI). Its text is prefixed with "[scripted demo LLM]".
"""

from fastapi import FastAPI, Request

from tests.fake_llm import ScriptedLLM

llm = ScriptedLLM(label=True)
app = FastAPI(title="Scripted demo LLM (not a real model)")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> dict:
    return llm.respond(await request.json())
