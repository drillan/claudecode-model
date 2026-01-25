"""Type definitions and conversion utilities for Claude Code CLI responses."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import NamedTuple, TypedDict

from claude_agent_sdk.types import Message

from pydantic import BaseModel, Field, model_validator
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from claudecode_model.exceptions import CLIResponseParseError

# JSON互換の再帰型（Any型を避ける）
type JsonValue = (
    int | float | str | bool | None | list[JsonValue] | dict[str, JsonValue]
)

# Message callback types for intermediate message access
MessageCallback = Callable[[Message], None]
AsyncMessageCallback = Callable[[Message], Awaitable[None]]
MessageCallbackType = MessageCallback | AsyncMessageCallback


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
        continue_conversation: Continue from the last conversation session.
            Overrides the value set in __init__ for this request.
            Cannot be used together with resume.
        resume: Session ID to resume. Cannot be used together with continue_conversation.
    """

    max_budget_usd: float
    append_system_prompt: str
    max_turns: int
    working_directory: str
    continue_conversation: bool
    resume: str


class ServerToolUse(BaseModel):
    """Server-side tool usage data from CLI response."""

    web_search_requests: int = Field(default=0, ge=0)
    web_fetch_requests: int = Field(default=0, ge=0)


class CacheCreation(BaseModel):
    """Cache creation details from CLI response."""

    ephemeral_1h_input_tokens: int = Field(default=0, ge=0)
    ephemeral_5m_input_tokens: int = Field(default=0, ge=0)


class PermissionDenial(BaseModel):
    """Permission denial entry from CLI response.

    Represents a denied tool usage permission with the tool name, input, and ID.
    """

    tool_name: str = Field(min_length=1)
    tool_input: dict[str, JsonValue] | None = None
    tool_use_id: str | None = None

    model_config = {"extra": "forbid"}


class ModelUsageData(BaseModel):
    """Per-model usage data from CLI response.

    Field names use snake_case internally with camelCase aliases for JSON compatibility.
    The CLI JSON response uses camelCase (e.g., inputTokens), but internal access
    uses snake_case (e.g., input_tokens).

    With populate_by_name=True, both formats are accepted for input:
        - camelCase (JSON format): ModelUsageData(inputTokens=100, ...)
        - snake_case (internal): ModelUsageData.model_validate({"input_tokens": 100, ...})

    Serialization:
        - model_dump(): returns snake_case keys
        - model_dump(by_alias=True): returns camelCase keys (for JSON output)
    """

    input_tokens: int = Field(ge=0, alias="inputTokens")
    output_tokens: int = Field(ge=0, alias="outputTokens")
    cache_read_input_tokens: int = Field(ge=0, alias="cacheReadInputTokens")
    cache_creation_input_tokens: int = Field(ge=0, alias="cacheCreationInputTokens")
    web_search_requests: int = Field(ge=0, alias="webSearchRequests")
    cost_usd: float = Field(ge=0, alias="costUSD")
    context_window: int = Field(ge=0, alias="contextWindow")
    max_output_tokens: int = Field(ge=0, alias="maxOutputTokens")

    model_config = {"extra": "forbid", "populate_by_name": True}


class ServerToolUseData(TypedDict, total=False):
    """TypedDict for server tool use data from JSON."""

    web_search_requests: int
    web_fetch_requests: int


class CacheCreationData(TypedDict, total=False):
    """TypedDict for cache creation data from JSON."""

    ephemeral_1h_input_tokens: int
    ephemeral_5m_input_tokens: int


class PermissionDenialData(TypedDict, total=False):
    """TypedDict for permission denial data from JSON."""

    tool_name: str
    tool_input: dict[str, JsonValue]
    tool_use_id: str | None


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
    permission_denials: list[PermissionDenialData]
    uuid: str
    structured_output: dict[str, JsonValue]
    errors: list[str]


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
    result: str = ""
    session_id: str | None = None
    total_cost_usd: float | None = None
    usage: CLIUsage
    model_usage: dict[str, ModelUsageData] | None = Field(
        default=None, alias="modelUsage"
    )
    permission_denials: list[PermissionDenial] | None = None
    uuid: str | None = None
    structured_output: dict[str, JsonValue] | None = None
    errors: list[str] | None = Field(
        default=None,
        description="Validation errors from --json-schema mode. "
        "When present, indicates schema validation issues occurred.",
    )

    model_config = {"extra": "forbid", "populate_by_name": True}

    @model_validator(mode="after")
    def validate_result_or_structured_output(self) -> "CLIResponse":
        """Ensure at least result or structured_output has meaningful content.

        Prevents silent failures where both result is empty and structured_output is None.
        Includes debug information in error message to help diagnose the issue.

        Note: Error subtypes (e.g., error_max_turns) are allowed to have empty results
        as they represent legitimate termination conditions.
        """
        # Allow empty results for error subtypes
        if self.subtype.startswith("error_"):
            return self

        if not self.result and self.structured_output is None:
            raise ValueError(
                "Either result must be non-empty or structured_output must be provided. "
                "Both cannot be empty/None simultaneously. "
                f"Debug info: is_error={self.is_error}, num_turns={self.num_turns}, "
                f"duration_ms={self.duration_ms}, subtype={self.subtype}"
            )
        return self

    def to_model_response(self, model_name: str | None = None) -> ModelResponse:
        """Convert CLI response to pydantic-ai ModelResponse.

        If structured_output is present, returns its JSON serialization.
        Otherwise returns the text result.

        Raises:
            CLIResponseParseError: If structured_output cannot be serialized to JSON.
        """
        # Use structured_output if available, otherwise use result
        if self.structured_output is not None:
            try:
                content = json.dumps(self.structured_output, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                raise CLIResponseParseError(
                    f"Failed to serialize structured_output to JSON: {e}",
                    raw_output=str(self.structured_output),
                ) from e
        else:
            content = self.result

        return ModelResponse(
            parts=[TextPart(content=content)],
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
