"""Errors with a stable code and exit status. Messages never contain values from a document."""

from __future__ import annotations

BAD_INPUT = 2
STORE_ERROR = 3
PRIVACY_ERROR = 4


class MxsatError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = BAD_INPUT):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
