"""claudecode-model: pydantic-ai Model implementation for Claude Code CLI."""

import logging
import os

# Configure log level from environment variable
# Users can set CLAUDECODE_MODEL_LOG_LEVEL=DEBUG to enable debug logging
_log_level = os.getenv("CLAUDECODE_MODEL_LOG_LEVEL", "WARNING").upper()
logging.getLogger("claudecode_model").setLevel(
    getattr(logging, _log_level, logging.WARNING)
)

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
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
    ClaudeCodeError,
    ErrorType,
    ToolNotFoundError,
    ToolsetNotRegisteredError,
    TypeHintResolutionError,
    UnsupportedDepsTypeError,
)
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
    CacheCreation,
    CLIResponse,
    CLIResponseData,
    CLIUsage,
    CLIUsageData,
    ClaudeCodeModelSettings,
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
    "CLIResponseParseError",
    "UnsupportedDepsTypeError",
    "TypeHintResolutionError",
    "ToolsetNotRegisteredError",
    "ToolNotFoundError",
    "ErrorType",
    "RequestWithMetadataResult",
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
