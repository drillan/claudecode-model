"""End-to-end tests for ClaudeCodeModel with actual SDK calls.

These tests require the `claude` command to be installed and accessible.
Tests are skipped if `claude` is not available.
"""

from __future__ import annotations

import shutil

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import ClaudeCodeModelSettings

# Skip tests if claude CLI is not installed; E2E tests require the real SDK
CLAUDE_AVAILABLE = shutil.which("claude") is not None

requires_claude = pytest.mark.skipif(
    not CLAUDE_AVAILABLE,
    reason="claude command not found. Install Claude Code CLI to run E2E tests.",
)


class TestClaudeCodeModelE2E:
    """End-to-end tests for ClaudeCodeModel using actual SDK calls."""

    @requires_claude
    @pytest.mark.asyncio
    async def test_simple_request_returns_response(self) -> None:
        """Simple request should return a valid ModelResponse."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[UserPromptPart(content="Reply with exactly: Hello E2E")]
            )
        ]
        params = ModelRequestParameters()

        response = await model.request(messages, None, params)

        assert response is not None
        assert len(response.parts) > 0
        # Verify response content is a non-empty string (TextPart)
        first_part = response.parts[0]
        assert hasattr(first_part, "content")
        assert isinstance(first_part.content, str)
        assert len(first_part.content) > 0

    @requires_claude
    @pytest.mark.asyncio
    async def test_request_with_system_prompt(self) -> None:
        """Request with system prompt should include it in the context."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="You are a helpful assistant."),
                    UserPromptPart(content="Say 'System prompt received'"),
                ]
            )
        ]
        params = ModelRequestParameters()

        response = await model.request(messages, None, params)

        assert response is not None
        assert len(response.parts) > 0

    @requires_claude
    @pytest.mark.asyncio
    async def test_request_with_metadata_returns_cli_response(self) -> None:
        """request_with_metadata should return both response and CLIResponse."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Reply with: Metadata test")])
        ]
        params = ModelRequestParameters()

        result = await model.request_with_metadata(messages, None, params)

        assert result.response is not None
        assert result.cli_response is not None
        assert result.cli_response.usage is not None
        assert result.cli_response.usage.input_tokens > 0
        assert result.cli_response.usage.output_tokens > 0
        assert result.cli_response.session_id is not None

    @requires_claude
    @pytest.mark.asyncio
    async def test_request_with_model_settings_timeout(self) -> None:
        """Request with custom timeout setting should complete successfully."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Reply with: Timeout test")])
        ]
        params = ModelRequestParameters()
        settings: ClaudeCodeModelSettings = {"timeout": 120.0}

        response = await model.request(messages, settings, params)

        assert response is not None

    @requires_claude
    @pytest.mark.asyncio
    async def test_request_with_working_directory(self) -> None:
        """Request should respect working_directory setting."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            working_directory="/tmp",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[UserPromptPart(content="Reply with: Working directory test")]
            )
        ]
        params = ModelRequestParameters()

        response = await model.request(messages, None, params)

        assert response is not None


class TestClaudeCodeModelE2EErrorHandling:
    """End-to-end tests for error handling scenarios."""

    @requires_claude
    @pytest.mark.asyncio
    async def test_empty_user_prompt_raises_value_error(self) -> None:
        """Empty user prompt should raise ValueError."""
        model = ClaudeCodeModel(
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="System only")])
        ]
        params = ModelRequestParameters()

        with pytest.raises(ValueError, match="No user prompt found"):
            await model.request(messages, None, params)
