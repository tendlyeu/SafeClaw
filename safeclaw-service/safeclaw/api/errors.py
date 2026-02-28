"""Structured error types for the SafeClaw API."""


class SafeClawError(Exception):
    """Structured API error with machine-readable code and human-readable hint."""

    def __init__(
        self,
        code: str,
        detail: str,
        hint: str = "",
        status_code: int = 500,
    ):
        self.code = code
        self.detail = detail
        self.hint = hint
        self.status_code = status_code
        super().__init__(detail)
