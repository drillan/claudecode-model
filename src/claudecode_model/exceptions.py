"""Custom exceptions for claudecode-model."""

from typing import Literal

# Supported error types for CLIExecutionError
ErrorType = Literal[
    "timeout",
    "permission",
    "cli_not_found",
    "invalid_response",
    "unknown",
]


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
            - "cli_not_found": CLI executable not found (not recoverable)
            - "invalid_response": Invalid/malformed response (not recoverable)
            - "unknown": Unknown error type (not recoverable)
            - None: Error type not determined (legacy or manual instantiation)
        recoverable: Whether the error may be recovered by retrying.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
        error_type: ErrorType | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr
        self.error_type = error_type
        self.recoverable = recoverable


class CLIInterruptedError(ClaudeCodeError):
    """Raised when execution is interrupted by the user (e.g., Ctrl-C).

    This exception is raised instead of raw KeyboardInterrupt to provide
    structured error handling. The subprocess is gracefully terminated
    (SIGTERM → wait → SIGKILL) before this exception is raised.
    """


class CLIResponseParseError(ClaudeCodeError):
    """Raised when CLI JSON output cannot be parsed."""

    def __init__(self, message: str, *, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output


class UnsupportedDepsTypeError(ClaudeCodeError):
    """Raised when a dependency type is not serializable.

    This error is raised when attempting to serialize a dependency type
    that is not supported (e.g., httpx.AsyncClient, database connections).

    Attributes:
        type_name: Name of the unsupported type for programmatic access.
    """

    def __init__(self, type_name: str) -> None:
        message = (
            f"Unsupported dependency type: {type_name}. "
            "Only serializable types are supported: "
            "dict, list, str, int, float, bool, None, dataclass, and Pydantic BaseModel."
        )
        super().__init__(message)
        self.type_name = type_name


class ToolsetNotRegisteredError(ClaudeCodeError):
    """Raised when function_tools are provided but no toolsets are registered.

    This error indicates that the user called request() or request_with_metadata()
    with function_tools in ModelRequestParameters, but never registered toolsets
    via model.set_agent_toolsets().

    Attributes:
        requested_tools: List of tool names that were requested.
    """

    def __init__(self, requested_tools: list[str]) -> None:
        message = (
            f"function_tools provided ({', '.join(requested_tools)}) "
            "but no toolsets are registered. "
            "Call model.set_agent_toolsets(agent._function_toolset) "
            "after creating the Agent to enable tool support."
        )
        super().__init__(message)
        self.requested_tools = requested_tools


class ToolNotFoundError(ClaudeCodeError):
    """Raised when requested tools are not found in registered toolsets.

    This error is raised when some of the tools specified in function_tools
    do not exist in the registered toolsets.

    Attributes:
        missing_tools: List of tool names that were not found.
        available_tools: List of tool names that are available in registered toolsets.
    """

    def __init__(self, missing_tools: list[str], available_tools: list[str]) -> None:
        message = (
            f"Tools not found in registered toolsets: {', '.join(missing_tools)}. "
            f"Available tools: {', '.join(available_tools) if available_tools else 'none'}. "
            "Make sure to call model.set_agent_toolsets(agent._function_toolset) "
            "after registering tools with @agent.tool or @agent.tool_plain."
        )
        super().__init__(message)
        self.missing_tools = missing_tools
        self.available_tools = available_tools


class TypeHintResolutionError(ClaudeCodeError):
    """Raised when type hints cannot be resolved for a dataclass.

    This error is raised when forward references in type hints
    cannot be resolved during serializability checking.

    Attributes:
        type_name: Name of the dataclass with unresolvable type hints.
        original_error: The original NameError that caused the resolution failure.
    """

    def __init__(self, type_name: str, original_error: NameError) -> None:
        message = (
            f"Cannot resolve type hints for dataclass '{type_name}': {original_error}. "
            "Ensure all referenced types are imported and available."
        )
        super().__init__(message)
        self.type_name = type_name
        self.original_error = original_error


class IPCError(ClaudeCodeError):
    """Base exception for IPC communication errors."""


class IPCConnectionError(IPCError):
    """Raised when the bridge process cannot connect to the IPC server."""


class IPCMessageSizeError(IPCError):
    """Raised when an IPC message exceeds MAX_MESSAGE_SIZE."""


class IPCToolExecutionError(IPCError):
    """Raised when a tool function raises an error during IPC execution."""


class BridgeStartupError(IPCError):
    """Raised when the bridge process fails to start."""


class StructuredOutputError(ClaudeCodeError):
    """Raised when structured output extraction fails after maximum retries.

    This error indicates that Claude Code CLI attempted to extract structured
    output matching the required schema multiple times but failed. This typically
    happens when the model outputs JSON in an unexpected format (e.g., wrapped
    in {"parameters": {...}} instead of top-level structure).

    To debug, check the session file at:
        ~/.claude/projects/<project-hash>/<session_id>.jsonl

    Attributes:
        session_id: Claude session ID for debugging.
        num_turns: Number of turns executed before failure.
        duration_ms: Total duration in milliseconds.
    """

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        num_turns: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.session_id = session_id
        self.num_turns = num_turns
        self.duration_ms = duration_ms
