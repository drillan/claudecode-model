"""Custom exceptions for claudecode-model."""


class ClaudeCodeError(Exception):
    """Base exception for claudecode-model."""


class CLINotFoundError(ClaudeCodeError):
    """Raised when the claude CLI is not found."""


class CLIExecutionError(ClaudeCodeError):
    """Raised when CLI execution fails (timeout, non-zero exit, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class CLIResponseParseError(ClaudeCodeError):
    """Raised when CLI JSON output cannot be parsed."""

    def __init__(self, message: str, *, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output
