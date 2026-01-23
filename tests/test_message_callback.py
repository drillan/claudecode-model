"""Tests for message callback functionality in ClaudeCodeModel."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk.types import AssistantMessage, Message, TextBlock
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import (
    AsyncMessageCallback,
    MessageCallback,
    MessageCallbackType,
)


class TestMessageCallbackTypes:
    """Tests for message callback type definitions."""

    def test_sync_callback_type_accepts_sync_function(self) -> None:
        """MessageCallback type should accept synchronous function."""
        received: list[Message] = []

        def sync_callback(msg: Message) -> None:
            received.append(msg)

        # Type check: ensure it matches MessageCallback
        callback: MessageCallback = sync_callback
        assert callback is not None

    def test_async_callback_type_accepts_async_function(self) -> None:
        """AsyncMessageCallback type should accept async function."""

        async def async_callback(msg: Message) -> None:
            pass

        # Type check: ensure it matches AsyncMessageCallback
        callback: AsyncMessageCallback = async_callback
        assert callback is not None

    def test_message_callback_type_accepts_both(self) -> None:
        """MessageCallbackType should accept both sync and async functions."""

        def sync_callback(msg: Message) -> None:
            pass

        async def async_callback(msg: Message) -> None:
            pass

        # Both should be assignable to MessageCallbackType
        callback1: MessageCallbackType = sync_callback
        callback2: MessageCallbackType = async_callback
        assert callback1 is not None
        assert callback2 is not None


class TestClaudeCodeModelMessageCallback:
    """Tests for ClaudeCodeModel message callback functionality."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response from SDK",
        )

    @pytest.fixture
    def mock_assistant_message(self) -> AssistantMessage:
        """Return a mock AssistantMessage."""
        return AssistantMessage(
            content=[TextBlock(text="Thinking about your question...")],
            model="claude-sonnet-4-20250514",
        )

    def test_constructor_accepts_message_callback(self) -> None:
        """ClaudeCodeModel should accept message_callback parameter."""
        received: list[Message] = []

        def callback(msg: Message) -> None:
            received.append(msg)

        model = ClaudeCodeModel(message_callback=callback)
        assert model._message_callback is callback

    def test_constructor_accepts_async_message_callback(self) -> None:
        """ClaudeCodeModel should accept async message_callback parameter."""

        async def async_callback(msg: Message) -> None:
            pass

        model = ClaudeCodeModel(message_callback=async_callback)
        assert model._message_callback is async_callback

    def test_constructor_without_callback(self) -> None:
        """ClaudeCodeModel should work without message_callback."""
        model = ClaudeCodeModel()
        assert model._message_callback is None

    @pytest.mark.asyncio
    async def test_callback_receives_assistant_message(
        self,
        mock_result_message: ResultMessage,
        mock_assistant_message: AssistantMessage,
    ) -> None:
        """Callback should receive AssistantMessage during execution."""
        received: list[Message] = []

        def callback(msg: Message) -> None:
            received.append(msg)

        model = ClaudeCodeModel(message_callback=callback)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield mock_assistant_message
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        # Callback should have received the AssistantMessage
        assert len(received) == 1
        assert isinstance(received[0], AssistantMessage)
        assert received[0].model == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(
        self,
        mock_result_message: ResultMessage,
        mock_assistant_message: AssistantMessage,
    ) -> None:
        """Async callback should be awaited during execution."""
        received: list[Message] = []

        async def async_callback(msg: Message) -> None:
            received.append(msg)

        model = ClaudeCodeModel(message_callback=async_callback)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield mock_assistant_message
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        # Async callback should have been awaited and received the message
        assert len(received) == 1
        assert isinstance(received[0], AssistantMessage)

    @pytest.mark.asyncio
    async def test_callback_receives_multiple_messages(
        self,
        mock_result_message: ResultMessage,
    ) -> None:
        """Callback should receive all intermediate messages."""
        received: list[Message] = []

        def callback(msg: Message) -> None:
            received.append(msg)

        model = ClaudeCodeModel(message_callback=callback)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        assistant_msg1 = AssistantMessage(
            content=[TextBlock(text="First response")],
            model="model-1",
        )
        assistant_msg2 = AssistantMessage(
            content=[TextBlock(text="Second response")],
            model="model-2",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield assistant_msg1
            yield assistant_msg2
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        # Should have received both AssistantMessages
        assert len(received) == 2
        assert isinstance(received[0], AssistantMessage)
        assert isinstance(received[1], AssistantMessage)
        assert received[0].model == "model-1"
        assert received[1].model == "model-2"

    @pytest.mark.asyncio
    async def test_no_callback_works_as_before(
        self,
        mock_result_message: ResultMessage,
        mock_assistant_message: AssistantMessage,
    ) -> None:
        """Model without callback should work exactly as before."""
        model = ClaudeCodeModel()  # No callback
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield mock_assistant_message
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

        # Should still return valid response
        assert response is not None
        assert len(response.parts) == 1

    @pytest.mark.asyncio
    async def test_callback_exception_is_logged_and_continues(
        self,
        mock_result_message: ResultMessage,
        mock_assistant_message: AssistantMessage,
    ) -> None:
        """Callback exception should be logged but not stop execution."""

        def failing_callback(msg: Message) -> None:
            raise ValueError("Callback error")

        model = ClaudeCodeModel(message_callback=failing_callback)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield mock_assistant_message
            yield mock_result_message

        # Should not raise, should complete successfully
        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

        assert response is not None


class TestClaudeCodeModelStreamMessages:
    """Tests for ClaudeCodeModel.stream_messages method."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response from SDK",
        )

    @pytest.fixture
    def mock_assistant_message(self) -> AssistantMessage:
        """Return a mock AssistantMessage."""
        return AssistantMessage(
            content=[TextBlock(text="Thinking...")],
            model="claude-sonnet-4-20250514",
        )

    @pytest.mark.asyncio
    async def test_stream_messages_yields_all_messages(
        self,
        mock_result_message: ResultMessage,
        mock_assistant_message: AssistantMessage,
    ) -> None:
        """stream_messages should yield all messages from SDK query."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            yield mock_assistant_message
            yield mock_result_message

        received: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for msg in model.stream_messages(messages, None, params):
                received.append(msg)

        # Should yield all messages including ResultMessage
        assert len(received) == 2
        assert isinstance(received[0], AssistantMessage)
        assert isinstance(received[1], ResultMessage)

    @pytest.mark.asyncio
    async def test_stream_messages_timeout(self) -> None:
        """stream_messages should raise CLIExecutionError on timeout."""
        model = ClaudeCodeModel(timeout=0.1)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        import anyio

        async def slow_query(**kwargs: object) -> AsyncIterator[Message]:
            await anyio.sleep(10)
            yield MagicMock()  # pragma: no cover

        with patch("claudecode_model.model.query", slow_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for _ in model.stream_messages(messages, None, params):
                    pass  # pragma: no cover

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_stream_messages_with_model_settings(
        self,
        mock_result_message: ResultMessage,
    ) -> None:
        """stream_messages should pass model_settings to SDK."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {
            "timeout": 30.0,
            "max_turns": 5,
        }

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[Message]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model.stream_messages(messages, settings, params):  # type: ignore[arg-type]
                pass

        assert len(captured_options) == 1
        assert captured_options[0].max_turns == 5
