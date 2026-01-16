"""pydantic-ai Model implementation for Claude Code CLI."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import Model

from claudecode_model.cli import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ClaudeCodeCLI,
)
from claudecode_model.types import CLIResponse, RequestWithMetadataResult

if TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)


class ClaudeCodeModel(Model):
    """pydantic-ai Model implementation using Claude Code CLI."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        working_directory: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self._model_name = model_name
        self._working_directory = working_directory
        self._timeout = timeout
        self._allowed_tools = allowed_tools
        self._disallowed_tools = disallowed_tools
        self._permission_mode = permission_mode
        self._max_turns = max_turns

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def system(self) -> str:
        """Return the system identifier for OpenTelemetry."""
        return "claude-code"

    def _extract_system_prompt(self, messages: list[ModelMessage]) -> str | None:
        """Extract system prompt from messages."""
        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, SystemPromptPart):
                        return part.content
        return None

    def _extract_user_prompt(self, messages: list[ModelMessage]) -> str:
        """Extract user prompt from the last message.

        Args:
            messages: List of conversation messages.

        Returns:
            Concatenated user prompt string.

        Raises:
            ValueError: If no user prompt is found in messages.
        """
        parts: list[str] = []

        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        content = part.content
                        if isinstance(content, str):
                            parts.append(content)
                        elif isinstance(content, Iterable) and not isinstance(
                            content, (str, bytes)
                        ):
                            for item in content:
                                if isinstance(item, str):
                                    parts.append(item)

        if not parts:
            raise ValueError(
                "No user prompt found in messages. "
                "Ensure at least one UserPromptPart with string content is provided."
            )

        return "\n".join(parts)

    async def _execute_request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
    ) -> CLIResponse:
        """Execute CLI request and return raw response.

        Internal method that handles the actual CLI execution logic.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).

        Returns:
            CLIResponse containing the raw CLI output with all metadata.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLINotFoundError: If the claude CLI is not found.
            CLIExecutionError: If CLI execution fails.
            CLIResponseParseError: If CLI output cannot be parsed.
        """
        system_prompt = self._extract_system_prompt(messages)
        user_prompt = self._extract_user_prompt(messages)

        # Extract settings from model_settings
        timeout = self._timeout
        max_budget_usd: float | None = None
        append_system_prompt: str | None = None
        max_turns: int | None = self._max_turns
        working_directory: str | None = self._working_directory

        if model_settings is not None:
            timeout_value = model_settings.get("timeout")
            if timeout_value is not None:
                if isinstance(timeout_value, (int, float)):
                    timeout = float(timeout_value)
                else:
                    logger.warning(
                        "model_settings 'timeout' has invalid type %s, "
                        "expected int or float. Using default timeout.",
                        type(timeout_value).__name__,
                    )

            max_budget_value = model_settings.get("max_budget_usd")
            if max_budget_value is not None:
                if isinstance(max_budget_value, (int, float)):
                    max_budget_usd = float(max_budget_value)
                    if max_budget_usd < 0:
                        raise ValueError("max_budget_usd must be non-negative")
                else:
                    logger.warning(
                        "model_settings 'max_budget_usd' has invalid type %s, "
                        "expected int or float. Ignoring this setting.",
                        type(max_budget_value).__name__,
                    )

            append_prompt_value = model_settings.get("append_system_prompt")
            if append_prompt_value is not None:
                if isinstance(append_prompt_value, str):
                    append_system_prompt = append_prompt_value
                else:
                    logger.warning(
                        "model_settings 'append_system_prompt' has invalid type %s, "
                        "expected str. Ignoring this setting.",
                        type(append_prompt_value).__name__,
                    )

            max_turns_value = model_settings.get("max_turns")
            if max_turns_value is not None:
                if isinstance(max_turns_value, int) and not isinstance(
                    max_turns_value, bool
                ):
                    if max_turns_value <= 0:
                        raise ValueError("max_turns must be a positive integer")
                    max_turns = max_turns_value
                else:
                    logger.warning(
                        "model_settings 'max_turns' has invalid type %s, "
                        "expected int. Ignoring this setting.",
                        type(max_turns_value).__name__,
                    )

            wd_value = model_settings.get("working_directory")
            if wd_value is not None:
                if isinstance(wd_value, str):
                    working_directory = wd_value
                else:
                    logger.warning(
                        "model_settings 'working_directory' has invalid type %s, "
                        "expected str. Using default working_directory.",
                        type(wd_value).__name__,
                    )

        cli = ClaudeCodeCLI(
            model=self._model_name,
            working_directory=working_directory,
            timeout=timeout,
            allowed_tools=self._allowed_tools,
            disallowed_tools=self._disallowed_tools,
            permission_mode=self._permission_mode,
            system_prompt=system_prompt,
            max_budget_usd=max_budget_usd,
            append_system_prompt=append_system_prompt,
            max_turns=max_turns,
        )

        return await cli.execute(user_prompt)

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request to Claude Code CLI.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).
            model_request_parameters: Request parameters for tools and output.

        Returns:
            ModelResponse containing the CLI response.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLINotFoundError: If the claude CLI is not found.
            CLIExecutionError: If CLI execution fails.
            CLIResponseParseError: If CLI output cannot be parsed.
        """
        cli_response = await self._execute_request(messages, model_settings)
        return cli_response.to_model_response(model_name=self._model_name)

    async def request_with_metadata(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> RequestWithMetadataResult:
        """Make a request to Claude Code CLI and return both response and metadata.

        This method is useful when you need access to CLI metadata such as
        total_cost_usd, duration_api_ms, num_turns, etc., which are lost
        during the to_model_response() conversion.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).
            model_request_parameters: Request parameters for tools and output.

        Returns:
            RequestWithMetadataResult containing:
                - response: ModelResponse for use with pydantic-ai Agent.
                - cli_response: Raw CLIResponse with full metadata.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLINotFoundError: If the claude CLI is not found.
            CLIExecutionError: If CLI execution fails.
            CLIResponseParseError: If CLI output cannot be parsed.

        Example:
            ```python
            model = ClaudeCodeModel()
            result = await model.request_with_metadata(messages, settings, params)
            metadata = {
                "total_cost_usd": result.cli_response.total_cost_usd,
                "num_turns": result.cli_response.num_turns,
                "duration_api_ms": result.cli_response.duration_api_ms,
            }
            ```
        """
        cli_response = await self._execute_request(messages, model_settings)
        return RequestWithMetadataResult(
            response=cli_response.to_model_response(model_name=self._model_name),
            cli_response=cli_response,
        )

    def __repr__(self) -> str:
        return f"ClaudeCodeModel(model_name={self._model_name!r})"
