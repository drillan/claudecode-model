"""Custom exceptions for claudecode-model."""


class ClaudeCodeError(Exception):
    """Base exception for claudecode-model."""


class CLINotFoundError(ClaudeCodeError):
    """Raised when the claude CLI is not found."""


class CLIExecutionError(ClaudeCodeError):
    """Raised when CLI execution fails (timeout, non-zero exit, etc.).

    Attributes:
        exit_code: CLI process exit code, if available.
        stderr: Standard error output from the CLI.
        error_type: Structured error type for programmatic handling.
            Supported values:
            - "timeout": Operation timed out (recoverable with longer timeout)
            - "permission": Permission denied error (not recoverable)
            - "rate_limit": Rate limit exceeded (recoverable after waiting)
            - "cli_not_found": CLI executable not found (not recoverable)
            - "invalid_response": Invalid/malformed response (not recoverable)
            - "unknown": Unknown error type (not recoverable)
        recoverable: Whether the error may be recovered by retrying.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
        error_type: str | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr
        self.error_type = error_type
        self.recoverable = recoverable


class CLIResponseParseError(ClaudeCodeError):
    """Raised when CLI JSON output cannot be parsed."""

    def __init__(self, message: str, *, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output
