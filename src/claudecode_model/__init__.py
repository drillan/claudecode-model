"""claudecode-model: pydantic-ai Model implementation for Claude Code CLI."""

from claudecode_model.cli import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_PROMPT_LENGTH,
    ClaudeCodeCLI,
)
from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
    ClaudeCodeError,
    ErrorType,
)
from claudecode_model.json_utils import extract_json
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.response_converter import (
    convert_sdk_messages_to_cli_response,
    convert_usage_dict_to_cli_usage,
    extract_text_from_assistant_message,
)
from claudecode_model.types import (
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
]


def main() -> None:
    """Entry point for the CLI (placeholder)."""
    print("Hello from claudecode-model!")
