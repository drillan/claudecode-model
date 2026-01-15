"""pydantic-ai Model implementation for Claude Code CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import Model

from claudecode_model.cli import ClaudeCodeCLI

if TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.settings import ModelSettings


class ClaudeCodeModel(Model):
    """pydantic-ai Model implementation using Claude Code CLI."""

    def __init__(
        self,
        model_name: str = "claude-sonnet-4-5",
        *,
        working_directory: str | None = None,
        timeout: float = 120.0,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._cli = ClaudeCodeCLI(
            model=model_name,
            working_directory=working_directory,
            timeout=timeout,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            permission_mode=permission_mode,
        )

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
        """Extract user prompt from the last message."""
        parts: list[str] = []

        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        content = part.content
                        if isinstance(content, str):
                            parts.append(content)
                        elif hasattr(content, "__iter__"):
                            for item in content:
                                if isinstance(item, str):
                                    parts.append(item)

        return "\n".join(parts) if parts else ""

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
        """
        system_prompt = self._extract_system_prompt(messages)
        user_prompt = self._extract_user_prompt(messages)

        if system_prompt:
            self._cli.system_prompt = system_prompt

        if model_settings and model_settings.get("timeout"):
            timeout_value = model_settings["timeout"]
            if isinstance(timeout_value, (int, float)):
                self._cli.timeout = float(timeout_value)

        cli_response = await self._cli.execute(user_prompt)
        return cli_response.to_model_response(model_name=self._model_name)

    def __repr__(self) -> str:
        return f"ClaudeCodeModel(model_name={self._model_name!r})"
