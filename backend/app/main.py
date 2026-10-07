"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.agent import build_llm_client
from app.api.routes import router
from app.config import Settings, load_settings
from app.errors import AppError
from app.services.debugger import DebugService
from app.services.history import HistoryStore
from app.tools.code_executor import build_executor

log = logging.getLogger("explain_my_error")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None, service: DebugService | None = None) -> FastAPI:
    """App factory. Tests pass in their own settings / service (e.g. with a scripted fake LLM)."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.service = service
        else:
            app.state.service = DebugService(
                settings=settings,
                executor=build_executor(settings),
                history=HistoryStore(settings.database_path),
                llm_client=build_llm_client(settings),
            )
        svc: DebugService = app.state.service
        if svc.model is None:
            log.warning("OPENAI_API_KEY is not set: 'Explain' falls back to static analysis and 'Fix' is disabled.")
        yield

    app = FastAPI(
        title="Explain My Error Like I'm Losing My Mind",
        description="Agentic AI debugging assistant (college project). Not a production-grade code sandbox.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        msg = str(first.get("msg", "Invalid request.")).removeprefix("Value error, ")
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return _error("validation_error", f"{msg} ({field})" if field and "paste" not in msg else msg, 422)

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", exc_info=exc)  # full trace stays in the server log only
        return _error("internal_error", "Something went wrong on the server.", 500)

    return app


app = create_app()
