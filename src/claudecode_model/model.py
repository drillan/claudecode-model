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
    ) -> None:
        self._model_name = model_name
        self._working_directory = working_directory
        self._timeout = timeout
        self._allowed_tools = allowed_tools
        self._disallowed_tools = disallowed_tools
        self._permission_mode = permission_mode

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

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request to Claude Code CLI.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (temperature, etc.).
            model_request_parameters: Request parameters for tools and output.

        Returns:
            ModelResponse containing the CLI response.

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

        cli = ClaudeCodeCLI(
            model=self._model_name,
            working_directory=self._working_directory,
            timeout=timeout,
            allowed_tools=self._allowed_tools,
            disallowed_tools=self._disallowed_tools,
            permission_mode=self._permission_mode,
            system_prompt=system_prompt,
            max_budget_usd=max_budget_usd,
            append_system_prompt=append_system_prompt,
        )

        cli_response = await cli.execute(user_prompt)
        return cli_response.to_model_response(model_name=self._model_name)

    def __repr__(self) -> str:
        return f"ClaudeCodeModel(model_name={self._model_name!r})"
