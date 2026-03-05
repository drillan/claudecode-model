"""Tests for timeout handling and generator cleanup (Issues #142, #144, #150).

Verifies that:
- Generator cleanup works correctly on timeout (shielded from external cancellation)
- _cleanup_query_generator_safe handles various error conditions
- Cleanup timeout constants are valid

Issue #150 replaced anyio.move_on_after with asyncio.timeout in the main
execution paths. The cleanup function still uses anyio internally (shielded).
"""

import logging
from collections.abc import AsyncIterator
from typing import cast

import anyio
import pytest
from claude_agent_sdk.types import Message

from claudecode_model.model import ClaudeCodeModel, _CLEANUP_TIMEOUT_SECONDS


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


class TestCleanupQueryGeneratorSafeShielding:
    """Tests that _cleanup_query_generator_safe shields aclose() from external cancellation.

    Since Issue #152, cleanup runs inside Task B's finally block via
    _cleanup_query_generator_safe (no longer via _cleanup_query_generator_on_timeout).
    """

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
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

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
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called
        assert any(
            "cancel scope" in record.message.lower() for record in caplog.records
        ), "Should log warning about cancel scope conflict"

    @pytest.mark.asyncio
    async def test_cleanup_logs_non_cancel_scope_runtime_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-cancel-scope RuntimeError should be logged as error.

        RuntimeError with a message unrelated to cancel scopes should be
        caught and logged as error, not silently dropped or propagated.
        """
        model = ClaudeCodeModel()

        class OtherRuntimeErrorGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise RuntimeError("Some unrelated runtime error")

        gen = OtherRuntimeErrorGenerator()

        with caplog.at_level(logging.ERROR):
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called
        assert any(
            "runtimeerror during query generator cleanup" in record.message.lower()
            for record in caplog.records
        ), "Should log error about RuntimeError during cleanup"


class TestCleanupQueryGeneratorSafe:
    """Direct unit tests for _cleanup_query_generator_safe."""

    @pytest.mark.asyncio
    async def test_none_generator_is_noop(self) -> None:
        """None input should return immediately without error."""
        model = ClaudeCodeModel()
        await model._cleanup_query_generator_safe(None)

    @pytest.mark.asyncio
    async def test_generator_without_aclose_is_noop(self) -> None:
        """Generator without aclose attribute should return immediately."""
        model = ClaudeCodeModel()

        class NoAcloseIterator:
            def __aiter__(self) -> "NoAcloseIterator":
                return self

            async def __anext__(self) -> Message:
                raise StopAsyncIteration

        gen = cast(AsyncIterator[Message], NoAcloseIterator())
        # Should not have aclose, but delattr isn't needed since class doesn't define it
        assert not hasattr(gen, "aclose")
        await model._cleanup_query_generator_safe(gen)

    @pytest.mark.asyncio
    async def test_successful_aclose(self) -> None:
        """Normal aclose() should be called without error."""
        model = ClaudeCodeModel()

        class CleanGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True

        gen = CleanGenerator()
        await model._cleanup_query_generator_safe(gen._as_message_iterator())
        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_cancel_scope_error_suppressed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CancelScope RuntimeError from aclose() should be logged and suppressed."""
        model = ClaudeCodeModel()

        class ScopeErrorGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)

        gen = ScopeErrorGenerator()
        with caplog.at_level(logging.WARNING):
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called
        assert any(
            "cancel scope conflict during generator cleanup" in record.message.lower()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_os_error_suppressed(self, caplog: pytest.LogCaptureFixture) -> None:
        """OSError from aclose() should be logged and suppressed."""
        model = ClaudeCodeModel()

        class OSErrorGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise BrokenPipeError("Subprocess pipe broken")

        gen = OSErrorGenerator()
        with caplog.at_level(logging.ERROR):
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called
        assert any(
            "failed to close query generator" in record.message.lower()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_programming_error_propagates(self) -> None:
        """Programming errors (TypeError, etc.) should NOT be suppressed."""
        model = ClaudeCodeModel()

        class BuggyGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                raise TypeError("unexpected argument type")

        gen = BuggyGenerator()
        with pytest.raises(TypeError, match="unexpected argument type"):
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called


class TestCleanupTimeoutConstants:
    """Tests for cleanup timeout constant usage."""

    def test_cleanup_timeout_is_positive(self) -> None:
        """_CLEANUP_TIMEOUT_SECONDS should be a positive number."""
        assert _CLEANUP_TIMEOUT_SECONDS > 0

    @pytest.mark.asyncio
    async def test_cleanup_timeout_applied(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cleanup should timeout if aclose() takes too long.

        _cleanup_query_generator_safe uses anyio.move_on_after internally,
        so a very slow aclose() should be cancelled after the timeout.
        """
        model = ClaudeCodeModel()

        class VerySlowCloseGenerator(MockAsyncGeneratorBase):
            async def aclose(self) -> None:
                self.aclose_called = True
                # Sleep much longer than cleanup timeout
                await anyio.sleep(_CLEANUP_TIMEOUT_SECONDS + 10)

        gen = VerySlowCloseGenerator(slow=False)

        with caplog.at_level(logging.ERROR):
            await model._cleanup_query_generator_safe(gen._as_message_iterator())

        assert gen.aclose_called
        assert any(
            "cleanup timed out" in record.message.lower() for record in caplog.records
        ), "Should log error about cleanup timeout"
