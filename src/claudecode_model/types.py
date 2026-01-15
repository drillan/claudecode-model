"""Type definitions and conversion utilities for Claude Code CLI responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.usage import RequestUsage


class CLIUsage(BaseModel):
    """Token usage information from CLI response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class CLIResponse(BaseModel):
    """Parsed response from Claude Code CLI JSON output."""

    type: str = "result"
    subtype: str = "success"
    is_error: bool = False
    duration_ms: int = 0
    duration_api_ms: int = 0
    num_turns: int = 1
    result: str = ""
    session_id: str | None = None
    total_cost_usd: float | None = None
    usage: CLIUsage = Field(default_factory=CLIUsage)

    model_config = {"extra": "ignore"}

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


def parse_cli_response(json_data: dict[str, Any]) -> CLIResponse:
    """Parse CLI JSON output into CLIResponse."""
    return CLIResponse.model_validate(json_data)
