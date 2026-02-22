"""claudecode-model: pydantic-ai Model implementation for Claude Code CLI."""

import logging
import os
import warnings

# Configure log level from environment variable
# Users can set CLAUDECODE_MODEL_LOG_LEVEL to DEBUG, INFO, WARNING, ERROR, or CRITICAL
# Default is WARNING (suppresses debug/info logs)
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_log_level_env = os.getenv("CLAUDECODE_MODEL_LOG_LEVEL")
_log_level_str = (_log_level_env or "WARNING").upper()

if _log_level_str not in _VALID_LOG_LEVELS:
    warnings.warn(
        f"Invalid CLAUDECODE_MODEL_LOG_LEVEL='{_log_level_str}'. "
        f"Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL. Using WARNING.",
        stacklevel=1,
    )
    _log_level_str = "WARNING"

_logger = logging.getLogger("claudecode_model")
_logger.setLevel(getattr(logging, _log_level_str))

# Add handler only when env var is explicitly set and no handler exists yet
# (prevents duplicate handlers on module reload)
if _log_level_env is not None and not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    _logger.addHandler(_handler)

from claudecode_model.cli import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_PROMPT_LENGTH,
    ClaudeCodeCLI,
)
from claudecode_model.deps_support import (  # noqa: E402
    DepsContext,
    create_deps_context,
    deserialize_deps,
    is_instance_serializable,
    is_serializable_type,
    serialize_deps,
)
from claudecode_model.exceptions import (  # noqa: E402
    BridgeStartupError,
    CLIExecutionError,
    CLIInterruptedError,
    CLINotFoundError,
    CLIResponseParseError,
    ClaudeCodeError,
    ErrorType,
    IPCConnectionError,
    IPCError,
    IPCMessageSizeError,
    IPCToolExecutionError,
    StructuredOutputError,
    ToolNotFoundError,
    ToolsetNotRegisteredError,
    TypeHintResolutionError,
    UnsupportedDepsTypeError,
)
from claudecode_model.ipc import DEFAULT_TRANSPORT, TransportType  # noqa: E402
from claudecode_model.json_utils import extract_json  # noqa: E402
from claudecode_model.model import ClaudeCodeModel  # noqa: E402
from claudecode_model.response_converter import (  # noqa: E402
    convert_sdk_messages_to_cli_response,
    convert_usage_dict_to_cli_usage,
    extract_text_from_assistant_message,
)
from claudecode_model.tool_converter import (  # noqa: E402
    JsonSchema,
    McpResponse,
    McpServerConfig,
    McpTextContent,
    convert_tool,
    convert_tool_with_deps,
    convert_tools_to_mcp_server,
)
from claudecode_model.types import (  # noqa: E402
    AsyncMessageCallback,
    CacheCreation,
    CLIResponse,
    CLIResponseData,
    CLIUsage,
    CLIUsageData,
    ClaudeCodeModelSettings,
    MessageCallback,
    MessageCallbackType,
    ModelUsageData,
    RequestWithMetadataResult,
    ServerToolUse,
)

__all__ = [
    "ClaudeCodeModel",
    "ClaudeCodeModelSettings",
    "ClaudeCodeCLI",
    "CLIResponse",
    "CLIResponseData",
    "CLIUsage",
    "CLIUsageData",
    "ClaudeCodeError",
    "CLINotFoundError",
    "CLIExecutionError",
    "CLIInterruptedError",
    "CLIResponseParseError",
    "StructuredOutputError",
    "UnsupportedDepsTypeError",
    "TypeHintResolutionError",
    "ToolsetNotRegisteredError",
    "ToolNotFoundError",
    "ErrorType",
    "RequestWithMetadataResult",
    "MessageCallback",
    "AsyncMessageCallback",
    "MessageCallbackType",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_PROMPT_LENGTH",
    "ServerToolUse",
    "CacheCreation",
    "ModelUsageData",
    "extract_json",
    "convert_sdk_messages_to_cli_response",
    "convert_usage_dict_to_cli_usage",
    "extract_text_from_assistant_message",
    "convert_tool",
    "convert_tool_with_deps",
    "convert_tools_to_mcp_server",
    "JsonSchema",
    "McpResponse",
    "McpServerConfig",
    "McpTextContent",
    # IPC bridge types
    "TransportType",
    "DEFAULT_TRANSPORT",
    # IPC exceptions
    "IPCError",
    "IPCConnectionError",
    "IPCMessageSizeError",
    "IPCToolExecutionError",
    "BridgeStartupError",
    # Serializable deps support (experimental)
    "DepsContext",
    "create_deps_context",
    "is_serializable_type",
    "is_instance_serializable",
    "serialize_deps",
    "deserialize_deps",
]


def main() -> None:
    """Entry point for the CLI (placeholder)."""
    print("Hello from claudecode-model!")
