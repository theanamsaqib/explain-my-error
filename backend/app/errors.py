"""Application-level errors that are safe to show to the user (never raw stack traces)."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class LLMError(AppError):
    """The LLM call failed or returned something unusable."""

    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(code, message, status_code)
