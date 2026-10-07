"""HTTP API. One consolidated debug endpoint (mode = explain | fix) plus an SSE stream for live progress."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.errors import AppError
from app.models.schemas import DebugRequest, DebugResponse, HealthResponse, HistoryItem
from app.services.debugger import DebugService

log = logging.getLogger("explain_my_error")
router = APIRouter(prefix="/api")


def get_service(request: Request) -> DebugService:
    return request.app.state.service


@router.get("/health", response_model=HealthResponse)
async def health(service: DebugService = Depends(get_service)) -> HealthResponse:
    s = service.settings
    return HealthResponse(
        llm_configured=service.model is not None,
        model=s.openai_model,
        execution_backend=type(service.executor).__name__.replace("Executor", "").lower(),
        max_attempts=s.max_attempts,
    )


@router.post("/debug", response_model=DebugResponse)
async def debug(req: DebugRequest, service: DebugService = Depends(get_service)) -> DebugResponse:
    """Run the whole workflow and return the final result in one response."""
    return await service.handle(req)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/debug/stream")
async def debug_stream(req: DebugRequest, service: DebugService = Depends(get_service)) -> StreamingResponse:
    """Same as POST /api/debug, but streams progress events (Server-Sent Events).

    Events: status, tool_call, attempt_started, attempt_running, attempt_result, then one of
    `result` (final DebugResponse) or `error`.
    """

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        task = asyncio.create_task(service.handle(req, queue.put_nowait))
        try:
            while not (task.done() and queue.empty()):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                yield _sse(event["type"], event)
            exc = task.exception()
            if exc is None:
                yield _sse("result", {"type": "result", "response": task.result().model_dump()})
            elif isinstance(exc, AppError):
                yield _sse("error", {"type": "error", "error": {"code": exc.code, "message": exc.message}})
            else:
                log.error("stream failed", exc_info=exc)
                yield _sse("error", {"type": "error", "error": {"code": "internal_error", "message": "Something went wrong on the server."}})
        finally:
            if not task.done():  # client disconnected
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/debug/history", response_model=list[HistoryItem])
async def history(limit: int = 30, service: DebugService = Depends(get_service)) -> list[HistoryItem]:
    return await service.history.list(max(1, min(limit, 100)))


@router.get("/debug/history/{session_id}", response_model=DebugResponse)
async def history_item(session_id: int, service: DebugService = Depends(get_service)) -> DebugResponse:
    item = await service.history.get(session_id)
    if item is None:
        raise AppError("not_found", "That debug session does not exist.", 404)
    return item
