"""Tests for anyio CancelScope nesting conflict fix (Issue #142).

Verifies that claudecode-model handles cancel scope tree corruption
caused by claude-agent-sdk's manual task group __aenter__/__aexit__
management when timeout cancellation interrupts _tg.__aexit__() completion.
"""

import logging
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import patch

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import Message
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel, _CLEANUP_TIMEOUT_SECONDS
from claudecode_model.types import ClaudeCodeModelSettings

# Error message pattern from anyio when cancel scope LIFO ordering is violated
_CANCEL_SCOPE_ERROR_MSG = (
    "Attempted to exit a cancel scope that isn't the "
    "current tasks's current cancel scope"
)


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
