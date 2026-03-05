"""Tests for SDK error classification and recoverable error handling (Issue #148).

Verifies that SDK error responses are correctly classified as recoverable
or unrecoverable based on the error content.
"""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk.types import ResultMessage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel

from .conftest import create_mock_result_message


class TestRecoverableErrorClassification:
    """Tests for recoverable flag on SDK error responses."""

    @pytest.mark.asyncio
    async def test_is_error_with_empty_result_is_recoverable(self) -> None:
        """is_error=True with empty result should be recoverable=True.

        When the SDK returns an error with no specific message, it is likely
        a transient issue. The caller should be able to decide to retry.
        """
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        error_result = create_mock_result_message(
            result="",
            is_error=True,
            subtype="error",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_request(messages, None)

        assert exc_info.value.recoverable is True
        assert exc_info.value.error_type == "invalid_response"
        assert "Unknown error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_is_error_with_none_result_is_recoverable(self) -> None:
        """is_error=True with None result should be recoverable=True."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        error_result = ResultMessage(
            subtype="error",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=True,
            num_turns=1,
            session_id="test-session",
            result=None,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_request(messages, None)

        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_is_error_with_nonempty_result_remains_unrecoverable(self) -> None:
        """is_error=True with specific error message should remain recoverable=False.

        When the SDK returns a concrete error message (e.g., rate limit),
        it represents a definite failure that retrying may not resolve.
        """
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        error_result = create_mock_result_message(
            result="Rate limit exceeded",
            is_error=True,
            subtype="error",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_request(messages, None)

        assert exc_info.value.recoverable is False
        assert "Rate limit exceeded" in str(exc_info.value)
