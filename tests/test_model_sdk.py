"""Tests for ClaudeCodeModel SDK integration and result message conversion."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import anyio
import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, UserMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, OutputObjectDefinition

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import ClaudeCodeModelSettings, RequestWithMetadataResult


class TestClaudeCodeModelResultMessageToCLIResponse:
    """Tests for ClaudeCodeModel._result_message_to_cli_response method."""

    def test_converts_basic_result_message(self) -> None:
        """_result_message_to_cli_response should convert basic ResultMessage."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1500,
            duration_api_ms=1200,
            is_error=False,
            num_turns=3,
            session_id="test-session-123",
            result="Hello from Claude",
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.type == "result"
        assert cli_response.subtype == "success"
        assert cli_response.is_error is False
        assert cli_response.duration_ms == 1500
        assert cli_response.duration_api_ms == 1200
        assert cli_response.num_turns == 3
        assert cli_response.session_id == "test-session-123"
        assert cli_response.result == "Hello from Claude"

    def test_converts_result_message_with_usage(self) -> None:
        """_result_message_to_cli_response should convert usage data."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 10,
                "cache_read_input_tokens": 5,
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.usage.input_tokens == 100
        assert cli_response.usage.output_tokens == 50
        assert cli_response.usage.cache_creation_input_tokens == 10
        assert cli_response.usage.cache_read_input_tokens == 5

    def test_converts_result_message_with_missing_usage(self) -> None:
        """_result_message_to_cli_response should handle missing usage."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage=None,
        )

        cli_response = model._result_message_to_cli_response(result)

        # Should default to 0 for all token counts
        assert cli_response.usage.input_tokens == 0
        assert cli_response.usage.output_tokens == 0
        assert cli_response.usage.cache_creation_input_tokens == 0
        assert cli_response.usage.cache_read_input_tokens == 0

    def test_converts_result_message_with_structured_output(self) -> None:
        """_result_message_to_cli_response should preserve structured_output."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="",
            structured_output={"name": "test", "score": 95},
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.structured_output is not None
        assert cli_response.structured_output["name"] == "test"
        assert cli_response.structured_output["score"] == 95

    def test_converts_result_message_with_cost(self) -> None:
        """_result_message_to_cli_response should preserve total_cost_usd."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            total_cost_usd=0.05,
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.total_cost_usd == 0.05

    def test_converts_result_message_with_server_tool_use(self) -> None:
        """_result_message_to_cli_response should convert server_tool_use in usage."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "server_tool_use": {
                    "web_search_requests": 3,
                    "web_fetch_requests": 2,
                },
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.usage.server_tool_use is not None
        assert cli_response.usage.server_tool_use.web_search_requests == 3
        assert cli_response.usage.server_tool_use.web_fetch_requests == 2

    def test_converts_result_message_with_cache_creation(self) -> None:
        """_result_message_to_cli_response should convert cache_creation in usage."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 10,
                "cache_read_input_tokens": 5,
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 1000,
                    "ephemeral_5m_input_tokens": 500,
                },
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.usage.cache_creation is not None
        assert cli_response.usage.cache_creation.ephemeral_1h_input_tokens == 1000
        assert cli_response.usage.cache_creation.ephemeral_5m_input_tokens == 500

    def test_converts_result_message_with_service_tier(self) -> None:
        """_result_message_to_cli_response should convert service_tier in usage."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "service_tier": "standard",
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.usage.service_tier == "standard"

    def test_converts_result_message_with_full_usage(self) -> None:
        """_result_message_to_cli_response should convert all usage fields."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_creation_input_tokens": 50,
                "cache_read_input_tokens": 25,
                "service_tier": "standard",
                "server_tool_use": {
                    "web_search_requests": 5,
                    "web_fetch_requests": 3,
                },
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 2000,
                    "ephemeral_5m_input_tokens": 800,
                },
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.usage.input_tokens == 200
        assert cli_response.usage.output_tokens == 100
        assert cli_response.usage.cache_creation_input_tokens == 50
        assert cli_response.usage.cache_read_input_tokens == 25
        assert cli_response.usage.service_tier == "standard"
        assert cli_response.usage.server_tool_use is not None
        assert cli_response.usage.server_tool_use.web_search_requests == 5
        assert cli_response.usage.server_tool_use.web_fetch_requests == 3
        assert cli_response.usage.cache_creation is not None
        assert cli_response.usage.cache_creation.ephemeral_1h_input_tokens == 2000
        assert cli_response.usage.cache_creation.ephemeral_5m_input_tokens == 800

    def test_usage_conversion_handles_unexpected_types_safely(self) -> None:
        """_result_message_to_cli_response should use _safe_int for type safety."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={
                "input_tokens": "100",  # string instead of int
                "output_tokens": 50.5,  # float instead of int
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )

        cli_response = model._result_message_to_cli_response(result)

        # _safe_int should convert string "100" to int 100
        assert cli_response.usage.input_tokens == 100
        # _safe_int should convert float 50.5 to int 50
        assert cli_response.usage.output_tokens == 50

    def test_converts_error_result_message(self) -> None:
        """_result_message_to_cli_response should preserve is_error flag."""
        model = ClaudeCodeModel()
        result = ResultMessage(
            subtype="error",
            duration_ms=500,
            duration_api_ms=400,
            is_error=True,
            num_turns=0,
            session_id="test-session",
            result="An error occurred",
        )

        cli_response = model._result_message_to_cli_response(result)

        assert cli_response.is_error is True
        assert cli_response.subtype == "error"
        assert cli_response.result == "An error occurred"


class TestClaudeCodeModelExecuteSDKQuery:
    """Tests for ClaudeCodeModel._execute_sdk_query method."""

    @pytest.mark.asyncio
    async def test_execute_sdk_query_returns_result_message(self) -> None:
        """_execute_sdk_query should return _QueryResult containing ResultMessage."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        expected_result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
        )

        async def mock_query(**kwargs: MagicMock) -> AsyncIterator[ResultMessage]:
            yield expected_result

        with patch("claudecode_model.model.query", mock_query):
            query_result = await model._execute_sdk_query(
                "Test prompt", options, timeout=60.0
            )

        assert query_result.result_message is expected_result
        assert query_result.captured_structured_output_input is None

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout(self) -> None:
        """_execute_sdk_query should raise CLIExecutionError on timeout."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def slow_query(**kwargs: object) -> AsyncIterator[object]:
            await anyio.sleep(10)  # Slow query that will timeout
            yield None  # pragma: no cover

        with patch("claudecode_model.model.query", slow_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_execute_sdk_query_raises_on_no_result_message(self) -> None:
        """_execute_sdk_query should raise CLIExecutionError when no ResultMessage."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def mock_query_no_result(**kwargs: object) -> AsyncIterator[UserMessage]:
            yield UserMessage(content="Some message")

        with patch("claudecode_model.model.query", mock_query_no_result):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert "No ResultMessage" in str(exc_info.value)


class TestClaudeCodeModelSDKIntegration:
    """Integration tests for ClaudeCodeModel with Claude Agent SDK."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return ResultMessage(
            subtype="success",
            duration_ms=1500,
            duration_api_ms=1200,
            is_error=False,
            num_turns=3,
            session_id="test-session-123",
            result="Response from SDK",
            total_cost_usd=0.05,
            usage={
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_creation_input_tokens": 50,
                "cache_read_input_tokens": 25,
            },
        )

    @pytest.mark.asyncio
    async def test_request_uses_sdk_query(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use Claude Agent SDK query() instead of CLI subprocess."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

        assert isinstance(response, ModelResponse)
        assert len(response.parts) == 1
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "Response from SDK"

    @pytest.mark.asyncio
    async def test_request_passes_system_prompt_to_sdk(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should pass system prompt to SDK options."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="Be helpful"),
                    UserPromptPart(content="Hello"),
                ]
            )
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        assert len(captured_options) == 1
        assert captured_options[0].system_prompt == "Be helpful"

    @pytest.mark.asyncio
    async def test_request_with_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should pass model_settings to SDK options."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {
            "max_budget_usd": 2.0,
            "max_turns": 5,
            "working_directory": "/custom/path",
            "append_system_prompt": "Be concise.",
        }

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

        assert len(captured_options) == 1
        assert captured_options[0].max_budget_usd == 2.0
        assert captured_options[0].max_turns == 5
        assert captured_options[0].cwd == "/custom/path"
        assert captured_options[0].system_prompt == "Be concise."

    @pytest.mark.asyncio
    async def test_request_with_json_schema(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should pass json_schema as output_format to SDK."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="native",
            output_object=OutputObjectDefinition(
                json_schema=json_schema,
                name="TestOutput",
                description="Test output",
                strict=True,
            ),
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        assert len(captured_options) == 1
        assert captured_options[0].output_format is not None
        assert captured_options[0].output_format["type"] == "json_schema"
        assert captured_options[0].output_format["schema"] == json_schema

    @pytest.mark.asyncio
    async def test_request_with_metadata_uses_sdk(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request_with_metadata should use SDK and preserve metadata."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

        assert isinstance(result, RequestWithMetadataResult)
        assert result.cli_response.total_cost_usd == 0.05
        assert result.cli_response.num_turns == 3
        assert result.cli_response.duration_api_ms == 1200
        assert result.cli_response.session_id == "test-session-123"


class TestClaudeCodeModelTimeoutCleanup:
    """Tests for subprocess cleanup on timeout."""

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_cleanup(self) -> None:
        """_execute_sdk_query should call aclose() on the generator when timeout occurs."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        aclose_called = False

        class MockAsyncGenerator:
            """Mock async generator that tracks aclose() calls."""

            def __init__(self) -> None:
                self._closed = False

            def __aiter__(self) -> "MockAsyncGenerator":
                return self

            async def __anext__(self) -> object:
                # Simulate a slow query that will timeout
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                nonlocal aclose_called
                aclose_called = True
                self._closed = True

        def mock_query(**kwargs: object) -> MockAsyncGenerator:
            return MockAsyncGenerator()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"
        assert aclose_called, "aclose() should be called on the generator when timeout"

    @pytest.mark.asyncio
    async def test_stream_messages_timeout_cleanup(self) -> None:
        """stream_messages should call aclose() on the generator when timeout occurs."""
        model = ClaudeCodeModel()
        aclose_called = False

        class MockAsyncGenerator:
            """Mock async generator that tracks aclose() calls."""

            def __init__(self) -> None:
                self._closed = False

            def __aiter__(self) -> "MockAsyncGenerator":
                return self

            async def __anext__(self) -> object:
                # Simulate a slow query that will timeout
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                nonlocal aclose_called
                aclose_called = True
                self._closed = True

        def mock_query(**kwargs: object) -> MockAsyncGenerator:
            return MockAsyncGenerator()

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

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"
        assert aclose_called, "aclose() should be called on the generator when timeout"

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_no_aclose_method(self) -> None:
        """_execute_sdk_query should handle generators without aclose() method."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class MockAsyncIteratorWithoutAclose:
            """Mock async iterator without aclose() method."""

            def __aiter__(self) -> "MockAsyncIteratorWithoutAclose":
                return self

            async def __anext__(self) -> object:
                # Simulate a slow query that will timeout
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

        def mock_query(**kwargs: object) -> MockAsyncIteratorWithoutAclose:
            return MockAsyncIteratorWithoutAclose()

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_aclose_raises_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_execute_sdk_query should log error when aclose() raises RuntimeError."""
        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        class MockAsyncGeneratorWithFailingAclose:
            """Mock async generator with aclose() that raises exception."""

            def __aiter__(self) -> "MockAsyncGeneratorWithFailingAclose":
                return self

            async def __anext__(self) -> object:
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                raise RuntimeError("Failed to close generator")

        def mock_query(**kwargs: object) -> MockAsyncGeneratorWithFailingAclose:
            return MockAsyncGeneratorWithFailingAclose()

        import logging

        with caplog.at_level(logging.ERROR):
            with patch("claudecode_model.model.query", mock_query):
                with pytest.raises(CLIExecutionError) as exc_info:
                    await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"
        assert any(
            "RuntimeError during query generator cleanup" in record.message
            for record in caplog.records
        ), "Should log error when aclose() raises RuntimeError"

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout_aclose_timeout(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_execute_sdk_query should log warning when aclose() times out."""
        from claudecode_model.model import _CLEANUP_TIMEOUT_SECONDS

        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()
        aclose_started = False

        class MockAsyncGeneratorWithSlowAclose:
            """Mock async generator with slow aclose() that will timeout."""

            def __aiter__(self) -> "MockAsyncGeneratorWithSlowAclose":
                return self

            async def __anext__(self) -> object:
                await anyio.sleep(10)
                raise StopAsyncIteration  # pragma: no cover

            async def aclose(self) -> None:
                nonlocal aclose_started
                aclose_started = True
                # Sleep longer than cleanup timeout
                await anyio.sleep(_CLEANUP_TIMEOUT_SECONDS + 5)

        def mock_query(**kwargs: object) -> MockAsyncGeneratorWithSlowAclose:
            return MockAsyncGeneratorWithSlowAclose()

        import logging

        with caplog.at_level(logging.WARNING):
            with patch("claudecode_model.model.query", mock_query):
                with pytest.raises(CLIExecutionError) as exc_info:
                    await model._execute_sdk_query("Test prompt", options, timeout=0.1)

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.error_type == "timeout"
        assert aclose_started, "aclose() should be called"
        assert any(
            "cleanup timed out" in record.message.lower() for record in caplog.records
        ), "Should log warning when aclose() times out"
