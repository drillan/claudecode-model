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
        working_directory: Working directory for the CLI execution.
            Overrides the value set in __init__ for this request.
    """

    max_budget_usd: float
    append_system_prompt: str
    max_turns: int
    working_directory: str


class ServerToolUse(BaseModel):
    """Server-side tool usage data from CLI response."""

    web_search_requests: int = Field(default=0, ge=0)
    web_fetch_requests: int = Field(default=0, ge=0)


class CacheCreation(BaseModel):
    """Cache creation details from CLI response."""

    ephemeral_1h_input_tokens: int = Field(default=0, ge=0)
    ephemeral_5m_input_tokens: int = Field(default=0, ge=0)


class ModelUsageData(BaseModel):
    """Per-model usage data from CLI response.

    Field names use snake_case internally with camelCase aliases for JSON compatibility.
    The CLI JSON response uses camelCase (e.g., inputTokens), but internal access
    uses snake_case (e.g., input_tokens).
    """

    input_tokens: int = Field(ge=0, alias="inputTokens")
    output_tokens: int = Field(ge=0, alias="outputTokens")
    cache_read_input_tokens: int = Field(ge=0, alias="cacheReadInputTokens")
    cache_creation_input_tokens: int = Field(ge=0, alias="cacheCreationInputTokens")
    web_search_requests: int = Field(ge=0, alias="webSearchRequests")
    cost_usd: float = Field(ge=0, alias="costUSD")
    context_window: int = Field(ge=0, alias="contextWindow")
    max_output_tokens: int = Field(ge=0, alias="maxOutputTokens")

    model_config = {"populate_by_name": True}


class ServerToolUseData(TypedDict, total=False):
    """TypedDict for server tool use data from JSON."""

    web_search_requests: int
    web_fetch_requests: int


class CacheCreationData(TypedDict, total=False):
    """TypedDict for cache creation data from JSON."""

    ephemeral_1h_input_tokens: int
    ephemeral_5m_input_tokens: int


class ModelUsageDataDict(TypedDict, total=False):
    """TypedDict for model usage data from JSON."""

    inputTokens: int
    outputTokens: int
    cacheReadInputTokens: int
    cacheCreationInputTokens: int
    webSearchRequests: int
    costUSD: float
    contextWindow: int
    maxOutputTokens: int


class CLIUsageData(TypedDict, total=False):
    """TypedDict for CLI usage data from JSON."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    server_tool_use: ServerToolUseData
    service_tier: str
    cache_creation: CacheCreationData


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
    model_usage: dict[str, ModelUsageDataDict]
    permission_denials: list[str]
    uuid: str


class CLIUsage(BaseModel):
    """Token usage information from CLI response."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0)
    server_tool_use: ServerToolUse | None = None
    service_tier: str | None = None
    cache_creation: CacheCreation | None = None


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
    model_usage: dict[str, ModelUsageData] | None = Field(
        default=None, alias="modelUsage"
    )
    permission_denials: list[str] | None = None
    uuid: str | None = None

    model_config = {"extra": "forbid", "populate_by_name": True}

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
