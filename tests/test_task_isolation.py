"""Tests for SDK query asyncio Task isolation (Issue #152).

Verifies that:
1. SDK query runs in a separate asyncio Task (Task B), isolated from caller (Task A)
2. Messages are correctly relayed from Task B to Task A via asyncio.Queue
3. _invoke_callback runs in Task A (caller's CancelScope context)
4. Errors from SDK are properly propagated to Task A
5. TimeoutError from SDK is re-raised (not wrapped as unknown)
6. asyncio.timeout cancels Task B and triggers cleanup
7. CancelledError triggers proper generator cleanup in Task B
8. End-to-end behavior of _execute_sdk_query and stream_messages is preserved
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import patch

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    Message,
    ResultMessage,
    ToolUseBlock,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import ClaudeCodeModelSettings

from .conftest import create_mock_result_message


class MockAsyncGeneratorBase:
    """Base class for mock async generators with configurable behavior."""

    def __init__(self, *, slow: bool = True) -> None:
        self._slow = slow
        self._closed = False
        self.aclose_called = False

    def __aiter__(self) -> "MockAsyncGeneratorBase":
        return self

    async def __anext__(self) -> Message:
        if self._slow:
            await anyio.sleep(10)
        raise StopAsyncIteration  # pragma: no cover

    def _as_message_iterator(self) -> AsyncIterator[Message]:
        """Cast self to AsyncIterator[Message] for type-safe test calls."""
        return cast(AsyncIterator[Message], self)


class TestRunSdkQueryIsolatedYieldsMessages:
    """Tests that _run_sdk_query_isolated correctly yields messages from SDK."""

    @pytest.mark.asyncio
    async def test_yields_intermediate_and_result_messages(self) -> None:
        """All messages from SDK should be yielded through the queue relay."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        assistant_msg = AssistantMessage(
            content=[],
            model="claude-sonnet-4-20250514",
        )

        class MultiMessageGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._messages: list[Message] = [assistant_msg, mock_result]
                self._index = 0

            async def __anext__(self) -> Message:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return MultiMessageGenerator()._as_message_iterator()

        collected: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for message in model._run_sdk_query_isolated("Test prompt", options):
                collected.append(message)

        assert len(collected) == 2
        assert collected[0] is assistant_msg
        assert collected[1] is mock_result

    @pytest.mark.asyncio
    async def test_skips_none_messages(self) -> None:
        """None messages from SDK should be filtered out."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        class NoneYieldingGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._messages: list[Message | None] = [None, mock_result, None]
                self._index = 0

            async def __anext__(self) -> Message:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg  # type: ignore[return-value]

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return NoneYieldingGenerator()._as_message_iterator()

        collected: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for message in model._run_sdk_query_isolated("Test prompt", options):
                collected.append(message)

        assert len(collected) == 1
        assert collected[0] is mock_result


class TestRunSdkQueryIsolatedTaskIsolation:
    """Tests that SDK query runs in a separate asyncio Task."""

    @pytest.mark.asyncio
    async def test_sdk_query_runs_in_different_task(self) -> None:
        """The SDK query generator should be iterated in a different asyncio Task."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        caller_task = asyncio.current_task()
        sdk_task_ids: list[int] = []

        class TaskTrackingGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> Message:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                current = asyncio.current_task()
                if current is not None:
                    sdk_task_ids.append(id(current))
                return mock_result

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return TaskTrackingGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model._run_sdk_query_isolated("Test", options):
                pass

        assert len(sdk_task_ids) == 1
        assert sdk_task_ids[0] != id(caller_task), (
            "SDK query should run in a different asyncio Task than the caller"
        )


class TestRunSdkQueryIsolatedErrorPropagation:
    """Tests that errors from SDK Task B are properly forwarded to Task A."""

    @pytest.mark.asyncio
    async def test_sdk_exception_forwarded_as_cli_execution_error(self) -> None:
        """Non-timeout exceptions from SDK should become CLIExecutionError(unknown)."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class ErrorGenerator(MockAsyncGeneratorBase):
            async def __anext__(self) -> Message:
                raise RuntimeError("SDK internal failure")

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return ErrorGenerator(slow=False)._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for _ in model._run_sdk_query_isolated("Test", options):
                    pass  # pragma: no cover

        assert exc_info.value.error_type == "unknown"
        assert "SDK internal failure" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sdk_timeout_error_re_raised(self) -> None:
        """TimeoutError from SDK should be re-raised directly, not wrapped."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class TimeoutGenerator(MockAsyncGeneratorBase):
            async def __anext__(self) -> Message:
                raise TimeoutError("SDK timeout")

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return TimeoutGenerator(slow=False)._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(TimeoutError, match="SDK timeout"):
                async for _ in model._run_sdk_query_isolated("Test", options):
                    pass  # pragma: no cover


class TestRunSdkQueryIsolatedCleanup:
    """Tests that generator cleanup runs in Task B on cancellation/completion."""

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_normal_completion(self) -> None:
        """Generator aclose should be called after normal iteration completes."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        class TrackingGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> Message:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

            async def aclose(self) -> None:
                self.aclose_called = True

        gen = TrackingGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model._run_sdk_query_isolated("Test", options):
                pass

        # Allow Task B's finally to complete
        await asyncio.sleep(0.1)
        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_caller_break(self) -> None:
        """Generator aclose should be called when caller breaks out of iteration."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        class InfiniteGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._count = 0

            async def __anext__(self) -> Message:
                self._count += 1
                if self._count > 100:
                    raise StopAsyncIteration
                return mock_result

            async def aclose(self) -> None:
                self.aclose_called = True

        gen = InfiniteGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model._run_sdk_query_isolated("Test", options):
                break  # Break after first message

        # Allow Task B's finally to complete
        await asyncio.sleep(0.1)
        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_timeout(self) -> None:
        """Generator aclose should be called when asyncio.timeout fires."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class SlowGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True

        gen = SlowGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.1):
                    async for _ in model._run_sdk_query_isolated("Test", options):
                        pass  # pragma: no cover

        # Allow Task B's finally to complete
        await asyncio.sleep(0.2)
        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_cancel_scope_error_during_cleanup_is_handled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CancelScope RuntimeError during cleanup should be caught and logged."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        class ScopeCorruptionGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> Message:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

            async def aclose(self) -> None:
                self.aclose_called = True
                raise RuntimeError(
                    "Attempted to exit a cancel scope that isn't the "
                    "current tasks's current cancel scope"
                )

        gen = ScopeCorruptionGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        with caplog.at_level(logging.WARNING):
            with patch("claudecode_model.model.query", mock_query):
                async for _ in model._run_sdk_query_isolated("Test", options):
                    pass

        # Allow Task B's finally to complete
        await asyncio.sleep(0.1)
        assert gen.aclose_called


class TestCallbackRunsInCallerTask:
    """Tests that _invoke_callback runs in Task A (caller's task), not Task B."""

    @pytest.mark.asyncio
    async def test_callback_executes_in_caller_task(self) -> None:
        """Message callback should execute in the same task as the caller."""
        caller_task = asyncio.current_task()
        callback_task_ids: list[int] = []

        def track_callback(message: Message) -> None:
            current = asyncio.current_task()
            if current is not None:
                callback_task_ids.append(id(current))

        model = ClaudeCodeModel(message_callback=track_callback)
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Done")

        assistant_msg = AssistantMessage(
            content=[],
            model="claude-sonnet-4-20250514",
        )

        class TwoMessageGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._messages: list[Message] = [assistant_msg, mock_result]
                self._index = 0

            async def __anext__(self) -> Message:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return TwoMessageGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            await model._execute_sdk_query("Test", options, timeout=60.0)

        assert len(callback_task_ids) == 1
        assert callback_task_ids[0] == id(caller_task), (
            "Callback should run in the caller's asyncio Task, not the SDK Task"
        )


class TestExecuteSdkQueryEndToEnd:
    """End-to-end tests for _execute_sdk_query with task isolation."""

    @pytest.mark.asyncio
    async def test_normal_query_returns_result(self) -> None:
        """Normal SDK query should return _QueryResult with ResultMessage."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Success")

        class SuccessGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> ResultMessage:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return SuccessGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            result = await model._execute_sdk_query("Test", options, timeout=60.0)

        assert result.result_message is mock_result

    @pytest.mark.asyncio
    async def test_timeout_raises_cli_execution_error(self) -> None:
        """Timeout should raise CLIExecutionError with error_type='timeout'."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return MockAsyncGeneratorBase()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test", options, timeout=0.1)

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_timeout_triggers_cleanup(self) -> None:
        """Timeout should trigger generator cleanup via Task B."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class TrackingGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True

        gen = TrackingGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError):
                await model._execute_sdk_query("Test", options, timeout=0.1)

        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_no_result_message_raises_error(self) -> None:
        """Query completing without ResultMessage should raise CLIExecutionError."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class EmptyGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)

            async def __anext__(self) -> Message:
                raise StopAsyncIteration

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return EmptyGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test", options, timeout=60.0)

        assert exc_info.value.error_type == "invalid_response"

    @pytest.mark.asyncio
    async def test_captures_structured_output_input(self) -> None:
        """StructuredOutput tool input should be captured during iteration."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        tool_input = {"key": "value"}
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-1",
                    name="StructuredOutput",
                    input=tool_input,
                )
            ],
            model="claude-sonnet-4-20250514",
        )
        mock_result = create_mock_result_message(result="Done")

        class StructuredOutputGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._messages: list[Message] = [assistant_msg, mock_result]
                self._index = 0

            async def __anext__(self) -> Message:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return StructuredOutputGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            result = await model._execute_sdk_query("Test", options, timeout=60.0)

        assert result.captured_structured_output_input == tool_input


class TestStreamMessagesEndToEnd:
    """End-to-end tests for stream_messages with task isolation."""

    @pytest.mark.asyncio
    async def test_normal_stream_yields_messages(self) -> None:
        """stream_messages should yield all SDK messages."""
        model = ClaudeCodeModel()
        mock_result = create_mock_result_message(result="Streamed")

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}

        collected: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for message in model.stream_messages(messages, settings, params):
                collected.append(message)

        assert len(collected) == 1
        assert collected[0] is mock_result

    @pytest.mark.asyncio
    async def test_stream_timeout_raises_cli_error(self) -> None:
        """Timeout in stream_messages should raise CLIExecutionError(timeout)."""
        model = ClaudeCodeModel()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return MockAsyncGeneratorBase()._as_message_iterator()

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 0.1}

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for _ in model.stream_messages(messages, settings, params):
                    pass  # pragma: no cover

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_stream_timeout_triggers_cleanup(self) -> None:
        """Timeout in stream_messages should trigger generator cleanup."""
        model = ClaudeCodeModel()

        class TrackingGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True

        gen = TrackingGenerator()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return gen._as_message_iterator()

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 0.1}

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError):
                async for _ in model.stream_messages(messages, settings, params):
                    pass  # pragma: no cover

        assert gen.aclose_called, (
            "aclose() should be called on the generator when stream_messages times out"
        )
