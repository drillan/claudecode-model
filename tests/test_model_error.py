"""Tests for ClaudeCodeModel error handling functionality."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)

from claudecode_model.exceptions import CLIExecutionError, StructuredOutputError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import JsonValue


class TestClaudeCodeModelIsErrorHandling:
    """Tests for is_error flag handling in _execute_request."""

    @pytest.mark.asyncio
    async def test_raises_cli_execution_error_when_is_error_true(self) -> None:
        """_execute_request should raise CLIExecutionError when is_error is True."""
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
            result="SDK error message",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_request(messages, None)

        assert "SDK reported error" in str(exc_info.value)
        assert exc_info.value.error_type == "invalid_response"
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_is_error_with_none_result(self) -> None:
        """_execute_request should handle is_error=True with None result."""
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

        assert "Unknown error" in str(exc_info.value)


class TestClaudeCodeModelSDKExceptionHandling:
    """Tests for SDK exception handling in _execute_sdk_query."""

    @pytest.mark.asyncio
    async def test_sdk_exception_wrapped_in_cli_execution_error(self) -> None:
        """_execute_sdk_query should wrap SDK exceptions in CLIExecutionError."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def mock_query_raises(**kwargs: object) -> AsyncIterator[object]:
            raise RuntimeError("SDK connection failed")
            yield  # pragma: no cover

        with patch("claudecode_model.model.query", mock_query_raises):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert "SDK query failed" in str(exc_info.value)
        assert "SDK connection failed" in str(exc_info.value)
        assert exc_info.value.error_type == "unknown"
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_sdk_exception_preserves_original_exception(self) -> None:
        """CLIExecutionError should chain the original SDK exception."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def mock_query_raises(**kwargs: object) -> AsyncIterator[object]:
            raise ValueError("Invalid API key")
            yield  # pragma: no cover

        with patch("claudecode_model.model.query", mock_query_raises):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestClaudeCodeModelUsageWarning:
    """Tests for usage data warning in _result_message_to_cli_response."""

    @pytest.mark.asyncio
    async def test_logs_warning_when_usage_is_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should log warning when usage is None."""
        model = ClaudeCodeModel()

        result_no_usage = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage=None,
        )

        with caplog.at_level(logging.WARNING):
            cli_response = model._result_message_to_cli_response(result_no_usage)

        assert "usage is None" in caplog.text
        assert cli_response.usage.input_tokens == 0
        assert cli_response.usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_no_warning_when_usage_present(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should not log warning when usage exists."""
        model = ClaudeCodeModel()

        result_with_usage = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        with caplog.at_level(logging.WARNING):
            cli_response = model._result_message_to_cli_response(result_with_usage)

        assert "usage is None" not in caplog.text
        assert cli_response.usage.input_tokens == 100
        assert cli_response.usage.output_tokens == 50


class TestResultMessageToCliResponseEmptyResultWarning:
    """Tests for warning log when ResultMessage has empty result."""

    def test_logs_warning_on_empty_result_and_no_structured_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should log warning when result is empty.

        When ResultMessage has empty result and no structured_output, a warning
        should be logged with debug info (is_error, num_turns, duration_ms, subtype).

        Note: Uses "invalid_subtype" (not "error_*") because error_ prefixed subtypes
        are now allowed to have empty results (Issue #86).
        """
        model = ClaudeCodeModel()

        result = ResultMessage(
            subtype="invalid_subtype",
            duration_ms=5000,
            duration_api_ms=4500,
            is_error=True,
            num_turns=3,
            session_id="test-session",
            result="",  # Empty result
            usage={"input_tokens": 100, "output_tokens": 50},
            structured_output=None,  # No structured output
        )

        with caplog.at_level(logging.WARNING), pytest.raises(ValueError):
            model._result_message_to_cli_response(result)

        # Verify warning was logged with debug info
        assert "empty result" in caplog.text
        assert "is_error=True" in caplog.text
        assert "num_turns=3" in caplog.text
        assert "duration_ms=5000" in caplog.text
        assert "subtype=invalid_subtype" in caplog.text

    def test_allows_empty_result_for_error_subtypes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should allow empty result for error_ subtypes.

        Error subtypes (e.g., error_max_turns) represent legitimate termination
        conditions and should be allowed to have empty results (Issue #86).
        """
        model = ClaudeCodeModel()

        result = ResultMessage(
            subtype="error_max_turns",
            duration_ms=5000,
            duration_api_ms=4500,
            is_error=True,
            num_turns=10,
            session_id="test-session",
            result="",  # Empty result
            usage={"input_tokens": 100, "output_tokens": 50},
            structured_output=None,  # No structured output
        )

        with caplog.at_level(logging.WARNING):
            cli_response = model._result_message_to_cli_response(result)

        # Should succeed without raising ValueError
        assert cli_response.subtype == "error_max_turns"
        assert cli_response.result == ""
        assert cli_response.structured_output is None

    def test_no_warning_when_result_is_present(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should not warn when result is non-empty."""
        model = ClaudeCodeModel()

        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Hello, world!",  # Non-empty result
            usage={"input_tokens": 100, "output_tokens": 50},
            structured_output=None,
        )

        with caplog.at_level(logging.WARNING):
            cli_response = model._result_message_to_cli_response(result)

        # Verify no warning about empty result
        assert "empty result" not in caplog.text
        assert cli_response.result == "Hello, world!"

    def test_no_warning_when_structured_output_is_present(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_result_message_to_cli_response should not warn when structured_output exists."""
        model = ClaudeCodeModel()

        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="",  # Empty result but structured_output exists
            usage={"input_tokens": 100, "output_tokens": 50},
            structured_output={"name": "test"},  # Has structured output
        )

        with caplog.at_level(logging.WARNING):
            cli_response = model._result_message_to_cli_response(result)

        # Verify no warning about empty result
        assert "empty result" not in caplog.text
        assert cli_response.structured_output == {"name": "test"}


class TestStructuredOutputError:
    """Tests for structured output retry exhaustion handling."""

    @pytest.mark.asyncio
    async def test_raises_structured_output_error_on_max_retries(self) -> None:
        """_execute_request should raise StructuredOutputError when max retries exceeded."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        # json_schema is required for recovery block to be entered
        json_schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        # Simulate SDK returning error_max_structured_output_retries
        error_result = ResultMessage(
            subtype="error_max_structured_output_retries",
            duration_ms=99031,
            duration_api_ms=98000,
            is_error=False,  # Note: is_error is False but subtype indicates failure
            num_turns=6,
            session_id="d5f9d990-27d2-4d6a-8925-cf7e043e6649",
            result="",  # Empty result
            structured_output=None,  # No structured output
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model._execute_request(messages, None, json_schema=json_schema)

        # Verify exception contains helpful information
        assert "recovery failed" in str(exc_info.value).lower()
        assert "error_max_structured_output_retries" in str(exc_info.value)
        assert exc_info.value.session_id == "d5f9d990-27d2-4d6a-8925-cf7e043e6649"
        assert exc_info.value.num_turns == 6
        assert exc_info.value.duration_ms == 99031

    @pytest.mark.asyncio
    async def test_logs_error_with_session_info_on_max_retries(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_execute_request should log error with session_id for debugging."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        # json_schema is required for recovery block to be entered
        json_schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        error_result = ResultMessage(
            subtype="error_max_structured_output_retries",
            duration_ms=99031,
            duration_api_ms=98000,
            is_error=False,
            num_turns=6,
            session_id="test-session-id-12345",
            result="",
            structured_output=None,
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with caplog.at_level(logging.ERROR):
            with patch("claudecode_model.model.query", mock_query):
                with pytest.raises(StructuredOutputError):
                    await model._execute_request(
                        messages, None, json_schema=json_schema
                    )

        # Verify error log contains session info for debugging
        assert "session_id=test-session-id-12345" in caplog.text
        assert "num_turns=6" in caplog.text
        assert "duration_ms=99031" in caplog.text
        assert ".jsonl" in caplog.text  # Should mention session file path

    def test_structured_output_error_attributes(self) -> None:
        """StructuredOutputError should have correct attributes."""
        error = StructuredOutputError(
            "Test message",
            session_id="test-session",
            num_turns=5,
            duration_ms=10000,
        )

        assert str(error) == "Test message"
        assert error.session_id == "test-session"
        assert error.num_turns == 5
        assert error.duration_ms == 10000

    def test_structured_output_error_optional_attributes(self) -> None:
        """StructuredOutputError should work with optional attributes."""
        error = StructuredOutputError("Test message")

        assert str(error) == "Test message"
        assert error.session_id is None
        assert error.num_turns is None
        assert error.duration_ms is None
