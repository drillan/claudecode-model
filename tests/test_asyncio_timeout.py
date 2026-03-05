"""Tests for asyncio.timeout replacement of anyio.move_on_after (Issue #150).

Verifies that:
1. TimeoutError from SDK is re-raised through except Exception guard
   (not wrapped as CLIExecutionError with error_type="unknown")
2. _had_cancel_scope_conflict flag is removed
3. Normal timeout behavior works with asyncio.timeout
4. stream_messages timeout works with asyncio.timeout
5. Cleanup (aclose) is called on timeout for both execution paths
6. Query completion just before timeout does not cause scope corruption
"""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import Message, ResultMessage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import ClaudeCodeModelSettings

from .conftest import create_mock_result_message
from .test_cancel_scope_fix import MockAsyncGeneratorBase


class TestTimeoutErrorReRaiseGuard:
    """Tests that TimeoutError is re-raised through except Exception guard.

    In the new implementation, run_query()'s except Exception block must
    re-raise TimeoutError instead of wrapping it as CLIExecutionError.
    This ensures asyncio.timeout's TimeoutError propagates to the outer
    except TimeoutError handler correctly.
    """

    @pytest.mark.asyncio
    async def test_sdk_timeout_error_treated_as_timeout_in_execute_sdk_query(
        self,
    ) -> None:
        """TimeoutError raised by SDK should result in error_type='timeout'.

        When the SDK or its internals raise TimeoutError, the except Exception
        guard should re-raise it. The outer except TimeoutError handler then
        converts it to CLIExecutionError with error_type="timeout".

        With the old code (move_on_after), TimeoutError from SDK would be
        wrapped as CLIExecutionError(error_type="unknown") since except
        Exception catches it and _is_cancel_scope_error returns False.
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class SDKTimeoutGenerator(MockAsyncGeneratorBase):
            async def __anext__(self) -> Message:
                raise TimeoutError("SDK internal timeout")

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return SDKTimeoutGenerator(slow=False)._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_sdk_timeout_error_treated_as_timeout_in_stream_messages(
        self,
    ) -> None:
        """TimeoutError raised by SDK in stream_messages should result in error_type='timeout'."""
        model = ClaudeCodeModel()

        class SDKTimeoutGenerator(MockAsyncGeneratorBase):
            async def __anext__(self) -> Message:
                raise TimeoutError("SDK internal timeout")

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return SDKTimeoutGenerator(slow=False)._as_message_iterator()

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

        assert exc_info.value.error_type == "timeout"


class TestCancelScopeConflictFlagRemoved:
    """Tests that _had_cancel_scope_conflict attribute is removed."""

    def test_no_cancel_scope_conflict_flag(self) -> None:
        """ClaudeCodeModel should not have _had_cancel_scope_conflict attribute.

        The asyncio.timeout replacement removes the need for tracking
        CancelScope conflicts since they can no longer occur.
        """
        model = ClaudeCodeModel()
        assert not hasattr(model, "_had_cancel_scope_conflict")


class TestAsyncioTimeoutBehavior:
    """Tests that asyncio.timeout is used for the main timeout scopes."""

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_raises_cli_error(self) -> None:
        """Timeout in _execute_sdk_query should raise CLIExecutionError(timeout)."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return MockAsyncGeneratorBase()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_calls_cleanup(self) -> None:
        """Timeout should call aclose() on the generator via cleanup."""
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
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert gen.aclose_called

    @pytest.mark.asyncio
    async def test_stream_messages_timeout_raises_cli_error(self) -> None:
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
                async for _ in model.stream_messages(
                    messages,
                    settings,
                    params,
                ):
                    pass  # pragma: no cover

        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_stream_messages_timeout_calls_cleanup(self) -> None:
        """Timeout in stream_messages should call aclose() on the generator."""
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
                async for _ in model.stream_messages(
                    messages,
                    settings,
                    params,
                ):
                    pass  # pragma: no cover

        assert gen.aclose_called, (
            "aclose() should be called on the generator when stream_messages times out"
        )

    @pytest.mark.asyncio
    async def test_normal_query_completes_successfully(self) -> None:
        """Normal query should complete without CancelScope error handling."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Success")

        class SuccessfulGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> ResultMessage:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return SuccessfulGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query(
                "Test prompt", options, timeout=60.0
            )

        assert query_result.result_message is mock_result

    @pytest.mark.asyncio
    async def test_normal_stream_completes_successfully(self) -> None:
        """Normal stream should complete without CancelScope error handling."""
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

        collected: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for message in model.stream_messages(
                messages,
                settings,
                params,
            ):
                collected.append(message)

        assert len(collected) == 1
        assert collected[0] is mock_result

    @pytest.mark.asyncio
    async def test_runtime_error_wrapped_as_unknown(self) -> None:
        """Non-timeout RuntimeError should be wrapped as CLIExecutionError(unknown)."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class RuntimeErrorGenerator(MockAsyncGeneratorBase):
            async def __anext__(self) -> Message:
                raise RuntimeError("Unrelated internal error")

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return RuntimeErrorGenerator(slow=False)._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert exc_info.value.error_type == "unknown"


class TestQueryCompletionBeforeTimeout:
    """Tests that query completing just before timeout returns normally.

    With the old move_on_after implementation, a query completing just before
    timeout could trigger CancelScope tree corruption (RuntimeError from
    move_on_after.__exit__()). With asyncio.timeout, this structural issue
    cannot occur because asyncio.timeout does not participate in the anyio
    scope tree.
    """

    @pytest.mark.asyncio
    async def test_fast_query_with_tight_timeout_succeeds(self) -> None:
        """Query that completes within timeout should return normally.

        Even with a tight timeout, a query that finishes in time should
        succeed without any scope-related errors.
        """
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        mock_result = create_mock_result_message(result="Just in time")

        class FastGenerator(MockAsyncGeneratorBase):
            def __init__(self) -> None:
                super().__init__(slow=False)
                self._yielded = False

            async def __anext__(self) -> ResultMessage:
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return mock_result

        def mock_query(**kwargs: object) -> AsyncIterator[Message]:
            return FastGenerator()._as_message_iterator()

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query(
                "Test prompt", options, timeout=0.5
            )

        assert query_result.result_message is mock_result

    @pytest.mark.asyncio
    async def test_fast_stream_with_tight_timeout_succeeds(self) -> None:
        """Stream that completes within timeout should yield all messages.

        With asyncio.timeout, there is no CancelScope conflict risk when
        the stream finishes just before the deadline.
        """
        model = ClaudeCodeModel()
        mock_result = create_mock_result_message(result="Streamed just in time")

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings: ClaudeCodeModelSettings = {"timeout": 0.5}

        collected: list[Message] = []
        with patch("claudecode_model.model.query", mock_query):
            async for message in model.stream_messages(
                messages,
                settings,
                params,
            ):
                collected.append(message)

        assert len(collected) == 1
        assert collected[0] is mock_result
