"""Tests for post-CancelScope conflict recovery (Issue #148).

Verifies that after a CancelScope conflict is handled (result preserved per
Issue #144), the error classification and diagnostic logging work correctly
for subsequent SDK requests.
"""

import logging
from collections.abc import AsyncIterator
from types import TracebackType
from unittest.mock import patch

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import ClaudeCodeModelSettings

from .conftest import create_mock_result_message

# Error message pattern from anyio when cancel scope LIFO ordering is violated
_CANCEL_SCOPE_ERROR_MSG = (
    "Attempted to exit a cancel scope that isn't the "
    "current tasks's current cancel scope"
)

# Save reference before any patching (evaluated at import time)
_real_anyio_move_on_after = anyio.move_on_after


class _CancelScopeErrorOnExit:
    """Context manager that simulates CancelScope corruption on __exit__()."""

    def __enter__(self) -> "_CancelScopeErrorOnExit":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        raise RuntimeError(_CANCEL_SCOPE_ERROR_MSG)


class _MockMoveOnAfterFirstCallError:
    """move_on_after mock that raises CancelScope error only on first call."""

    def __init__(self) -> None:
        self._first = True

    def __call__(self, delay: float) -> _CancelScopeErrorOnExit | anyio.CancelScope:
        if self._first:
            self._first = False
            return _CancelScopeErrorOnExit()
        return _real_anyio_move_on_after(delay)


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


class TestCancelScopeConflictFlag:
    """Tests for _had_cancel_scope_conflict instance flag."""

    @pytest.mark.asyncio
    async def test_cancel_scope_flag_set_after_conflict(self) -> None:
        """_had_cancel_scope_conflict should be True after CancelScope conflict.

        When _execute_sdk_query handles a CancelScope conflict and preserves
        the result (Issue #144 path), the flag should be set for diagnostic
        correlation with subsequent errors.
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Success from SDK")

        class SuccessfulGenerator:
            def __init__(self) -> None:
                self._yielded = False
                self.aclose_called = False

            def __aiter__(self) -> "SuccessfulGenerator":
                return self

            async def __anext__(self) -> ResultMessage:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

            async def aclose(self) -> None:
                self.aclose_called = True

        gen_instance = SuccessfulGenerator()

        def mock_query(**kwargs: object) -> SuccessfulGenerator:
            return gen_instance

        assert model._had_cancel_scope_conflict is False

        with (
            patch("claudecode_model.model.query", mock_query),
            patch(
                "claudecode_model.model.anyio.move_on_after",
                _MockMoveOnAfterFirstCallError(),
            ),
        ):
            await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert model._had_cancel_scope_conflict is True

    @pytest.mark.asyncio
    async def test_cancel_scope_flag_cleared_on_normal_success(self) -> None:
        """_had_cancel_scope_conflict should be False after normal successful request.

        When a request succeeds without any CancelScope conflict or SDK error,
        the flag should be cleared to avoid false correlation with future errors.
        Flag is cleared in _execute_request after the is_error check passes.
        """
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        # Simulate a prior CancelScope conflict
        model._had_cancel_scope_conflict = True

        mock_result = create_mock_result_message(result="Normal success")

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result

        with patch("claudecode_model.model.query", mock_query):
            await model._execute_request(messages, None)

        assert model._had_cancel_scope_conflict is False

    @pytest.mark.asyncio
    async def test_post_conflict_empty_error_logs_correlation_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log correlation warning when empty error follows CancelScope conflict.

        When _had_cancel_scope_conflict is True and the next query returns
        is_error=True with empty result, a warning should be logged connecting
        the two events for diagnostic purposes.
        """
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        # Simulate a prior CancelScope conflict
        model._had_cancel_scope_conflict = True

        error_result = create_mock_result_message(
            result="",
            is_error=True,
            subtype="error",
            session_id="test-session-148",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with caplog.at_level(logging.WARNING):
            with patch("claudecode_model.model.query", mock_query):
                with pytest.raises(CLIExecutionError):
                    await model._execute_request(messages, None)

        assert any(
            "CancelScope conflict" in record.message
            and "empty result" in record.message
            for record in caplog.records
        ), "Should log correlation warning linking CancelScope conflict to empty error"

    @pytest.mark.asyncio
    async def test_stream_cancel_scope_conflict_sets_flag(self) -> None:
        """_had_cancel_scope_conflict should be True after streaming CancelScope conflict.

        When stream_messages handles a CancelScope conflict after a completed
        stream (Issue #144 streaming path), the flag should be set.
        """
        model = ClaudeCodeModel()
        mock_result = create_mock_result_message(result="Streamed success")

        class CompletedStreamGenerator:
            def __init__(self) -> None:
                self._messages: list[ResultMessage] = [mock_result]
                self._index = 0
                self.aclose_called = False

            def __aiter__(self) -> "CompletedStreamGenerator":
                return self

            async def __anext__(self) -> ResultMessage:
                if self._index >= len(self._messages):
                    raise StopAsyncIteration
                msg = self._messages[self._index]
                self._index += 1
                return msg

            async def aclose(self) -> None:
                self.aclose_called = True

        gen_instance = CompletedStreamGenerator()

        def mock_query(**kwargs: object) -> CompletedStreamGenerator:
            return gen_instance

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}

        assert model._had_cancel_scope_conflict is False

        with (
            patch("claudecode_model.model.query", mock_query),
            patch(
                "claudecode_model.model.anyio.move_on_after",
                _MockMoveOnAfterFirstCallError(),
            ),
        ):
            async for _ in model.stream_messages(messages, settings, params):
                pass

        assert model._had_cancel_scope_conflict is True

    @pytest.mark.asyncio
    async def test_stream_normal_success_clears_flag(self) -> None:
        """_had_cancel_scope_conflict should be False after normal streaming success.

        When stream_messages completes without any CancelScope conflict,
        the flag should be cleared to prevent false correlation.
        """
        model = ClaudeCodeModel()
        mock_result = create_mock_result_message(result="Streamed success")

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

        # Simulate a prior CancelScope conflict
        model._had_cancel_scope_conflict = True

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model.stream_messages(messages, settings, params):
                pass

        assert model._had_cancel_scope_conflict is False

    @pytest.mark.asyncio
    async def test_nonempty_error_clears_flag(self) -> None:
        """_had_cancel_scope_conflict should be False after non-empty error.

        When a non-empty error occurs (e.g., "Rate limit exceeded"), it is
        a definite SDK failure unrelated to CancelScope aftermath. The flag
        should be cleared to prevent false correlation with future errors.
        """
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Test")])
        ]

        # Simulate a prior CancelScope conflict
        model._had_cancel_scope_conflict = True

        error_result = create_mock_result_message(
            result="Rate limit exceeded",
            is_error=True,
            subtype="error",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError):
                await model._execute_request(messages, None)

        assert model._had_cancel_scope_conflict is False
