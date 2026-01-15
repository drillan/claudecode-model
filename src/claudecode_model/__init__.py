"""claudecode-model: pydantic-ai Model implementation for Claude Code CLI."""

from claudecode_model.cli import ClaudeCodeCLI
from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
    ClaudeCodeError,
)
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import CLIResponse

__all__ = [
    "ClaudeCodeModel",
    "ClaudeCodeCLI",
    "CLIResponse",
    "ClaudeCodeError",
    "CLINotFoundError",
    "CLIExecutionError",
    "CLIResponseParseError",
]


def main() -> None:
    """Entry point for the CLI (placeholder)."""
    print("Hello from claudecode-model!")
