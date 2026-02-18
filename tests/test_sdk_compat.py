"""Tests for SDK compatibility layer handling unknown message types."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk._errors import MessageParseError
from claude_agent_sdk.types import AssistantMessage, Message, TextBlock
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart

from pydantic_ai.models import ModelRequestParameters

from claudecode_model._sdk_compat import (
    _UNKNOWN_TYPE_PREFIX,
    _safe_parse_message,
    safe_message_parsing,
)
from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel


class TestSafeParseMessage:
    """Tests for _safe_parse_message function."""

    def test_returns_none_for_unknown_message_type(self) -> None:
        """_safe_parse_message should return None for unknown message types."""
        data: dict[str, object] = {"type": "rate_limit_event", "retry_after": 5}
        result = _safe_parse_message(data)
        assert result is None

    def test_returns_none_for_arbitrary_unknown_type(self) -> None:
        """_safe_parse_message should return None for any unknown message type."""
        data: dict[str, object] = {"type": "some_future_event", "data": "value"}
        result = _safe_parse_message(data)
        assert result is None

    def test_logs_warning_for_unknown_message_type(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_safe_parse_message should log warning with type and full data."""
        data: dict[str, object] = {"type": "rate_limit_event", "retry_after": 5}
        with caplog.at_level(logging.WARNING):
            _safe_parse_message(data)
        assert "Skipping unrecognized SDK message type" in caplog.text
        assert "rate_limit_event" in caplog.text
        # M1: Verify full data is logged for debugging
        assert "retry_after" in caplog.text

    def test_raises_for_missing_required_field(self) -> None:
        """_safe_parse_message should re-raise for missing required fields."""
        data: dict[str, object] = {"type": "assistant", "message": {}}
        with pytest.raises(MessageParseError, match="Missing required field"):
            _safe_parse_message(data)

    def test_raises_for_missing_type_field(self) -> None:
        """_safe_parse_message should re-raise when type field is missing."""
        data: dict[str, object] = {}
        with pytest.raises(MessageParseError, match="missing 'type' field"):
            _safe_parse_message(data)

    def test_passes_through_valid_result_message(self) -> None:
        """_safe_parse_message should return valid Message for known types."""
        data: dict[str, object] = {
            "type": "result",
            "subtype": "success",
            "duration_ms": 1000,
            "duration_api_ms": 800,
            "is_error": False,
            "num_turns": 1,
            "session_id": "test",
        }
        result = _safe_parse_message(data)
        assert isinstance(result, ResultMessage)

    def test_unknown_type_prefix_matches_sdk_error_message(self) -> None:
        """_UNKNOWN_TYPE_PREFIX should match the SDK's actual error message format.

        This test validates that the SDK's message_parser.py still uses the
        expected error format. If the SDK changes its wording, this test will
        fail, alerting us that the prefix match needs updating.
        When the prefix no longer matches, the code fails safe (re-raises).
        """
        from claude_agent_sdk._internal.message_parser import parse_message

        with pytest.raises(MessageParseError) as exc_info:
            parse_message({"type": "nonexistent_test_type"})
        assert str(exc_info.value).startswith(_UNKNOWN_TYPE_PREFIX)


class TestSafeMessageParsingContextManager:
    """Tests for safe_message_parsing context manager."""

    def test_patches_parse_message_in_client_module(self) -> None:
        """safe_message_parsing should patch parse_message in the SDK client module."""
        from claude_agent_sdk._internal import client as sdk_client

        original = sdk_client.parse_message
        with safe_message_parsing():
            assert sdk_client.parse_message is not original
        # Restored after exit
        assert sdk_client.parse_message is original

    def test_patched_parse_message_returns_none_for_unknown(self) -> None:
        """Patched parse_message should return None for unknown types."""
        from claude_agent_sdk._internal import client as sdk_client

        with safe_message_parsing():
            result = sdk_client.parse_message(
                {"type": "rate_limit_event", "retry_after": 5}
            )
            assert result is None

    def test_patched_parse_message_still_parses_known_types(self) -> None:
        """Patched parse_message should still parse known types correctly."""
        from claude_agent_sdk._internal import client as sdk_client

        with safe_message_parsing():
            result = sdk_client.parse_message(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 1000,
                    "duration_api_ms": 800,
                    "is_error": False,
                    "num_turns": 1,
                    "session_id": "test",
                }
            )
            assert isinstance(result, ResultMessage)


class TestExecuteSDKQueryWithUnknownMessage:
    """Tests for unknown message handling in _execute_sdk_query."""

    @pytest.mark.asyncio
    async def test_skips_unknown_message_and_receives_result(self) -> None:
        """_execute_sdk_query should skip unknown messages and get ResultMessage."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Hello",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        async def mock_query(
            **kwargs: object,
        ) -> AsyncIterator[Message | None]:
            yield None  # Simulates unknown message patched to None
            yield result_msg

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query("Test", options, timeout=60.0)

        assert query_result.result_message is result_msg
        assert query_result.result_message.result == "Hello"
        assert query_result.result_message.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_multiple_unknown_messages_before_result(self) -> None:
        """_execute_sdk_query should skip multiple unknown messages."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=2,
            session_id="test-session",
            result="Result after multiple unknowns",
            usage={"input_tokens": 200, "output_tokens": 100},
        )

        async def mock_query(
            **kwargs: object,
        ) -> AsyncIterator[Message | None]:
            yield None  # rate_limit_event
            yield None  # some_other_event
            yield result_msg

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query("Test", options, timeout=60.0)

        assert query_result.result_message.result == "Result after multiple unknowns"

    @pytest.mark.asyncio
    async def test_unknown_between_assistant_and_result(self) -> None:
        """_execute_sdk_query should handle unknown message between assistant and result."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-sonnet-4-20250514",
        )

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Hello",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        callback_messages: list[Message] = []

        async def mock_callback(message: Message) -> None:
            callback_messages.append(message)

        model._message_callback = mock_callback  # type: ignore[assignment]

        async def mock_query(
            **kwargs: object,
        ) -> AsyncIterator[Message | None]:
            yield assistant_msg
            yield None  # Unknown message between assistant and result
            yield result_msg

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query("Test", options, timeout=60.0)

        assert query_result.result_message is result_msg
        # AssistantMessage callback should have been invoked
        assert len(callback_messages) == 1
        assert callback_messages[0] is assistant_msg


class TestStreamMessagesWithUnknownMessage:
    """Tests for unknown message handling in stream_messages."""

    @pytest.mark.asyncio
    async def test_stream_messages_filters_none(self) -> None:
        """stream_messages should not yield None (unknown) messages."""
        model = ClaudeCodeModel()

        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Response")],
            model="claude-sonnet-4-20250514",
        )

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Done",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        async def mock_query(
            **kwargs: object,
        ) -> AsyncIterator[Message | None]:
            yield assistant_msg
            yield None  # Unknown message
            yield result_msg

        received: list[Message] = []
        messages: list[ModelRequest | ModelResponse] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]
        params = ModelRequestParameters()
        with patch("claudecode_model.model.query", mock_query):
            async for msg in model.stream_messages(messages, None, params):
                received.append(msg)

        # Should receive assistant + result, NOT None
        assert len(received) == 2
        assert isinstance(received[0], AssistantMessage)
        assert isinstance(received[1], ResultMessage)

    @pytest.mark.asyncio
    async def test_stream_messages_filters_multiple_consecutive_none(self) -> None:
        """stream_messages should skip multiple consecutive None messages."""
        model = ClaudeCodeModel()

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Done",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        async def mock_query(
            **kwargs: object,
        ) -> AsyncIterator[Message | None]:
            yield None  # rate_limit_event
            yield None  # some_other_event
            yield None  # yet_another_event
            yield result_msg

        received: list[Message] = []
        messages: list[ModelRequest | ModelResponse] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]
        params = ModelRequestParameters()
        with patch("claudecode_model.model.query", mock_query):
            async for msg in model.stream_messages(messages, None, params):
                received.append(msg)

        assert len(received) == 1
        assert isinstance(received[0], ResultMessage)

    @pytest.mark.asyncio
    async def test_stream_messages_sdk_exception_becomes_cli_execution_error(
        self,
    ) -> None:
        """stream_messages should wrap SDK exceptions in CLIExecutionError."""
        model = ClaudeCodeModel()

        async def mock_query_raises(**kwargs: object) -> AsyncIterator[Message]:
            raise RuntimeError("SDK transport error")
            yield  # pragma: no cover

        messages: list[ModelRequest | ModelResponse] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]
        params = ModelRequestParameters()
        with patch("claudecode_model.model.query", mock_query_raises):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for _ in model.stream_messages(messages, None, params):
                    pass  # pragma: no cover

        assert "SDK query failed" in str(exc_info.value)
        assert "SDK transport error" in str(exc_info.value)
