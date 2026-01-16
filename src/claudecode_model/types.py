"""Type definitions and conversion utilities for Claude Code CLI responses."""

from __future__ import annotations

from typing import NamedTuple, TypedDict

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage


class ClaudeCodeModelSettings(ModelSettings, total=False):
    """Extended ModelSettings for Claude Code CLI.

    Inherits from pydantic-ai ModelSettings and adds Claude CLI-specific options.

    Attributes:
        timeout: Request timeout in seconds (inherited from ModelSettings).
        max_budget_usd: Maximum budget in USD for the request.
        append_system_prompt: Additional system prompt to append.
        max_turns: Maximum number of turns for the CLI execution.
    """

    max_budget_usd: float
    append_system_prompt: str
    max_turns: int


class CLIUsageData(TypedDict, total=False):
    """TypedDict for CLI usage data from JSON."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


class CLIResponseData(TypedDict, total=False):
    """TypedDict for CLI JSON response data."""

    type: str
    subtype: str
    is_error: bool
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    result: str
    session_id: str | None
    total_cost_usd: float | None
    usage: CLIUsageData


class CLIUsage(BaseModel):
    """Token usage information from CLI response."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0)


class CLIResponse(BaseModel):
    """Parsed response from Claude Code CLI JSON output."""

    type: str
    subtype: str
    is_error: bool
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    result: str
    session_id: str | None = None
    total_cost_usd: float | None = None
    usage: CLIUsage

    model_config = {"extra": "forbid"}

    def to_model_response(self, model_name: str | None = None) -> ModelResponse:
        """Convert CLI response to pydantic-ai ModelResponse."""
        return ModelResponse(
            parts=[TextPart(content=self.result)],
            usage=RequestUsage(
                input_tokens=self.usage.input_tokens,
                output_tokens=self.usage.output_tokens,
                cache_write_tokens=self.usage.cache_creation_input_tokens,
                cache_read_tokens=self.usage.cache_read_input_tokens,
            ),
            model_name=model_name,
        )


class RequestWithMetadataResult(NamedTuple):
    """Result from request_with_metadata containing both response and CLI metadata.

    Attributes:
        response: The pydantic-ai ModelResponse for use with Agent.
        cli_response: The raw CLIResponse with full metadata (duration, cost, turns, etc).
    """

    response: ModelResponse
    cli_response: CLIResponse


def parse_cli_response(json_data: CLIResponseData) -> CLIResponse:
    """Parse CLI JSON output into CLIResponse.

    Args:
        json_data: The JSON data from CLI output.

    Returns:
        Validated CLIResponse object.

    Raises:
        pydantic.ValidationError: If required fields are missing or invalid.
    """
    return CLIResponse.model_validate(json_data)
