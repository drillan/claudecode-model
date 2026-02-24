"""Tests for anyio CancelScope nesting conflict fix (Issues #142, #144).

Verifies that claudecode-model handles cancel scope tree corruption
caused by claude-agent-sdk's manual task group __aenter__/__aexit__
management when timeout cancellation interrupts _tg.__aexit__() completion.

Issue #144 extends this to verify that successful query results are
preserved when CancelScope RuntimeError occurs after query completion.
"""

import logging
from collections.abc import AsyncIterator
from types import TracebackType
from typing import cast
from unittest.mock import patch

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import Message, ResultMessage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel, _CLEANUP_TIMEOUT_SECONDS
from claudecode_model.types import ClaudeCodeModelSettings

from .conftest import create_mock_result_message

# Error message pattern from anyio when cancel scope LIFO ordering is violated
_CANCEL_SCOPE_ERROR_MSG = (
    "Attempted to exit a cancel scope that isn't the "
    "current tasks's current cancel scope"
)


class _CancelScopeErrorOnExit:
    """Context manager that simulates CancelScope corruption on __exit__().

    Used to reproduce the scenario where move_on_after.__exit__() encounters
    a stale CancelScope from claude-agent-sdk's internal task group, raising
    RuntimeError even though the query completed successfully (Issue #144).
    """

    def __enter__(self) -> "_CancelScopeErrorOnExit":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)


def _mock_move_on_after_with_error(delay: float) -> _CancelScopeErrorOnExit:
    """Factory that returns a context manager raising RuntimeError on exit."""
    return _CancelScopeErrorOnExit()


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


class TestCleanupQueryGeneratorOnTimeoutShielding:
    """Tests that _cleanup_query_generator_on_timeout shields aclose() from external cancellation."""

    @pytest.mark.asyncio
    async def test_shielded_cleanup_completes_despite_external_cancel(self) -> None:
        """aclose() should complete even when external cancellation is active.

        Simulates pydantic-graph's outer cancel scope firing during cleanup.
        The shield should protect aclose() from being interrupted.
        """
        model = ClaudeCodeModel()
        aclose_completed = False

        class SlowCloseGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                nonlocal aclose_completed
                self.aclose_called = True
                # Simulate SDK cleanup that takes time
                await anyio.sleep(0.5)
                aclose_completed = True

        gen = SlowCloseGenerator()

        # Run cleanup inside an external cancel scope that fires quickly
        # (simulating pydantic-graph's outer timeout)
        with anyio.CancelScope(shield=True):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._cleanup_query_generator_on_timeout(
                    gen._as_message_iterator(), timeout=5.0
                )

        assert exc_info.value.error_type == "timeout"
        assert gen.aclose_called
        assert aclose_completed, "aclose() should complete inside shielded scope"

    @pytest.mark.asyncio
    async def test_cleanup_catches_cancel_scope_runtime_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cleanup should catch RuntimeError from SDK cancel scope corruption.

        When aclose() triggers process_query's finally block and _tg.__aexit__()
        fails due to scope tree corruption, the RuntimeError should be caught
        and logged as a warning, not propagated.
        """
        model = ClaudeCodeModel()

        class ScopeCorruptionGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)

        gen = ScopeCorruptionGenerator()

        with caplog.at_level(logging.WARNING):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._cleanup_query_generator_on_timeout(
                    gen._as_message_iterator(), timeout=5.0
                )

        assert exc_info.value.error_type == "timeout"
        assert gen.aclose_called
        assert any(
            "cancel scope" in record.message.lower() for record in caplog.records
        ), "Should log warning about cancel scope conflict"

    @pytest.mark.asyncio
    async def test_cleanup_propagates_non_cancel_scope_runtime_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-cancel-scope RuntimeError should be logged (not suppressed silently).

        RuntimeError with a message unrelated to cancel scopes should still
        be caught and logged (same behavior as other exceptions), not silently dropped.
        """
        model = ClaudeCodeModel()

        class OtherRuntimeErrorGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise RuntimeError("Some unrelated runtime error")

        gen = OtherRuntimeErrorGenerator()

        with caplog.at_level(logging.ERROR):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._cleanup_query_generator_on_timeout(
                    gen._as_message_iterator(), timeout=5.0
                )

        # Should still raise CLIExecutionError (timeout), not the RuntimeError
        assert exc_info.value.error_type == "timeout"
        assert gen.aclose_called
        assert any(
            "failed to close query generator" in record.message.lower()
            for record in caplog.records
        ), "Should log error about failed generator close"


class TestExecuteSdkQueryCancelScopeHandling:
    """Tests that _execute_sdk_query handles cancel scope RuntimeError from SDK."""

    @pytest.mark.asyncio
    async def test_cancel_scope_runtime_error_treated_as_timeout(self) -> None:
        """RuntimeError from cancel scope corruption should be treated as timeout.

        When move_on_after.__exit__() raises RuntimeError because _tg's cancel scope
        is still current (not properly popped by _tg.__aexit__()), the error should
        be caught and converted to CLIExecutionError with timeout type.
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class ScopeCorruptingGenerator:
            """Generator that simulates SDK cancel scope corruption on timeout."""

            def __aiter__(self) -> "ScopeCorruptingGenerator":
                return self

            async def __anext__(self) -> object:
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                # Simulate the RuntimeError that occurs when move_on_after.__exit__()
                # finds _tg's scope still on the stack
                raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)

        def mock_query(**kwargs: object) -> ScopeCorruptingGenerator:
            return ScopeCorruptingGenerator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_non_cancel_scope_runtime_error_propagated(self) -> None:
        """Non-cancel-scope RuntimeError should propagate unchanged.

        RuntimeError with messages unrelated to cancel scopes should not be
        caught by the cancel scope handling.
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class UnrelatedErrorGenerator:
            def __aiter__(self) -> "UnrelatedErrorGenerator":
                return self

            async def __anext__(self) -> object:
                raise RuntimeError("Unrelated internal error")

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> UnrelatedErrorGenerator:
            return UnrelatedErrorGenerator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        # Should be wrapped as CLIExecutionError by run_query's except Exception handler
        assert exc_info.value.error_type == "unknown"

    @pytest.mark.asyncio
    async def test_cancel_scope_error_after_successful_query_returns_result(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CancelScope RuntimeError after successful query should return result.

        When run_query() completes successfully and query_result is assigned,
        but move_on_after.__exit__() raises RuntimeError due to stale CancelScope
        from SDK's task group, the result should be preserved and returned
        instead of being discarded as a false timeout (Issue #144).
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Success from SDK")

        class SuccessfulGenerator:
            """Generator that yields a ResultMessage and completes normally."""

            def __init__(self) -> None:
                self._yielded = False

            def __aiter__(self) -> "SuccessfulGenerator":
                return self

            async def __anext__(self) -> ResultMessage:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> SuccessfulGenerator:
            return SuccessfulGenerator()

        with caplog.at_level(logging.WARNING):
            with (
                patch("claudecode_model.model.query", mock_query),
                patch(
                    "claudecode_model.model.anyio.move_on_after",
                    _mock_move_on_after_with_error,
                ),
            ):
                query_result = await model._execute_sdk_query(
                    "Test prompt", options, timeout=60.0
                )

        assert query_result.result_message is mock_result
        assert query_result.captured_structured_output_input is None
        assert any(
            "result preserved" in record.message.lower() for record in caplog.records
        ), "Should log warning that result was preserved despite cancel scope conflict"

    @pytest.mark.asyncio
    async def test_cancel_scope_error_after_successful_query_with_structured_output(
        self,
    ) -> None:
        """Preserved result should include captured_structured_output_input.

        When the query includes StructuredOutput tool use and CancelScope
        RuntimeError occurs after completion, the captured structured output
        input must also be preserved (Issue #144).
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Structured result")
        structured_input: dict[str, object] = {"key": "value", "nested": {"a": 1}}

        class StructuredOutputGenerator:
            """Generator that yields AssistantMessage with StructuredOutput then ResultMessage."""

            def __init__(self) -> None:
                self._phase = 0

            def __aiter__(self) -> "StructuredOutputGenerator":
                return self

            async def __anext__(self) -> Message:
                if self._phase == 0:
                    # Yield AssistantMessage with StructuredOutput tool use
                    from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

                    self._phase = 1
                    return AssistantMessage(
                        model="claude-sonnet-4-20250514",
                        content=[
                            ToolUseBlock(
                                id="tool-1",
                                name="StructuredOutput",
                                input=structured_input,
                            )
                        ],
                    )
                elif self._phase == 1:
                    self._phase = 2
                    return mock_result
                raise StopAsyncIteration

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> StructuredOutputGenerator:
            return StructuredOutputGenerator()

        with (
            patch("claudecode_model.model.query", mock_query),
            patch(
                "claudecode_model.model.anyio.move_on_after",
                _mock_move_on_after_with_error,
            ),
        ):
            query_result = await model._execute_sdk_query(
                "Test prompt", options, timeout=60.0
            )

        assert query_result.result_message is mock_result
        assert query_result.captured_structured_output_input == structured_input


class TestStreamMessagesCancelScopeHandling:
    """Tests that stream_messages handles cancel scope RuntimeError from SDK."""

    @pytest.mark.asyncio
    async def test_cancel_scope_runtime_error_treated_as_timeout(self) -> None:
        """RuntimeError from cancel scope corruption should be treated as timeout in stream_messages."""
        model = ClaudeCodeModel()

        class ScopeCorruptingGenerator:
            def __aiter__(self) -> "ScopeCorruptingGenerator":
                return self

            async def __anext__(self) -> object:
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)

        def mock_query(**kwargs: object) -> ScopeCorruptingGenerator:
            return ScopeCorruptingGenerator()

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
                async for _ in model.stream_messages(
                    messages,
                    settings,
                    params,
                ):
                    pass  # pragma: no cover

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_non_cancel_scope_runtime_error_propagated(self) -> None:
        """Non-cancel-scope RuntimeError should propagate in stream_messages."""
        model = ClaudeCodeModel()

        class UnrelatedErrorGenerator:
            def __aiter__(self) -> "UnrelatedErrorGenerator":
                return self

            async def __anext__(self) -> object:
                raise RuntimeError("Unrelated internal error")

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> UnrelatedErrorGenerator:
            return UnrelatedErrorGenerator()

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for _ in model.stream_messages(
                    messages,
                    settings,
                    params,
                ):
                    pass  # pragma: no cover

        # Should be wrapped as CLIExecutionError by the except Exception handler
        assert exc_info.value.error_type == "unknown"

    @pytest.mark.asyncio
    async def test_cancel_scope_error_after_complete_stream_returns_normally(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CancelScope RuntimeError after completed stream should not raise timeout.

        When all messages have been yielded successfully and the async for loop
        completes naturally, but move_on_after.__exit__() raises RuntimeError
        due to stale CancelScope from SDK's task group, the generator should
        terminate normally without raising CLIExecutionError (Issue #144).
        """
        model = ClaudeCodeModel()
        mock_result = create_mock_result_message(result="Streamed success")

        class CompletedStreamGenerator:
            """Generator that yields messages then completes normally."""

            def __init__(self) -> None:
                self._messages: list[ResultMessage] = [mock_result]
                self._index = 0

            def __aiter__(self) -> "CompletedStreamGenerator":
                return self

            async def __anext__(self) -> ResultMessage:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> CompletedStreamGenerator:
            return CompletedStreamGenerator()

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}

        collected: list[Message] = []
        with caplog.at_level(logging.WARNING):
            with (
                patch("claudecode_model.model.query", mock_query),
                patch(
                    "claudecode_model.model.anyio.move_on_after",
                    _mock_move_on_after_with_error,
                ),
            ):
                async for message in model.stream_messages(
                    messages,
                    settings,
                    params,
                ):
                    collected.append(message)

        assert len(collected) == 1
        assert collected[0] is mock_result
        assert any(
            "results preserved" in record.message.lower() for record in caplog.records
        ), "Should log warning that stream results were preserved"

    @pytest.mark.asyncio
    async def test_cancel_scope_error_after_multi_message_stream(self) -> None:
        """Multiple messages should all be preserved when CancelScope error occurs after stream completion."""
        model = ClaudeCodeModel()
        from claude_agent_sdk.types import AssistantMessage, TextBlock

        mock_assistant = AssistantMessage(
            model="claude-sonnet-4-20250514",
            content=[TextBlock(text="Thinking...")],
        )
        mock_result = create_mock_result_message(result="Final answer")

        class MultiMessageGenerator:
            """Generator that yields multiple messages then completes."""

            def __init__(self) -> None:
                self._messages: list[Message] = [mock_assistant, mock_result]
                self._index = 0

            def __aiter__(self) -> "MultiMessageGenerator":
                return self

            async def __anext__(self) -> Message:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

            async def aclose(self) -> None:
                pass

        def mock_query(**kwargs: object) -> MultiMessageGenerator:
            return MultiMessageGenerator()

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}

        collected: list[Message] = []
        with (
            patch("claudecode_model.model.query", mock_query),
            patch(
                "claudecode_model.model.anyio.move_on_after",
                _mock_move_on_after_with_error,
            ),
        ):
            async for message in model.stream_messages(
                messages,
                settings,
                params,
            ):
                collected.append(message)

        assert len(collected) == 2
        assert collected[0] is mock_assistant
        assert collected[1] is mock_result


class TestCleanupTimeoutConstants:
    """Tests for cleanup timeout constant usage."""

    def test_cleanup_timeout_is_positive(self) -> None:
        """_CLEANUP_TIMEOUT_SECONDS should be a positive number."""
        assert _CLEANUP_TIMEOUT_SECONDS > 0

    @pytest.mark.asyncio
    async def test_cleanup_timeout_applied(self) -> None:
        """Cleanup should timeout if aclose() takes too long."""
        model = ClaudeCodeModel()

        class VerySlowCloseGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                # Sleep much longer than cleanup timeout
                await anyio.sleep(_CLEANUP_TIMEOUT_SECONDS + 10)

        gen = VerySlowCloseGenerator(slow=False)

        with pytest.raises(CLIExecutionError) as exc_info:
            await model._cleanup_query_generator_on_timeout(
                gen._as_message_iterator(), timeout=5.0
            )

        assert exc_info.value.error_type == "timeout"
        assert gen.aclose_called
