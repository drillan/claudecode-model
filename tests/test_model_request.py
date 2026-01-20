"""Tests for ClaudeCodeModel request methods."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

from claudecode_model.exceptions import ToolNotFoundError, ToolsetNotRegisteredError
from claudecode_model.model import ClaudeCodeModel

from .conftest import create_mock_result_message


class TestClaudeCodeModelRequest:
    """Tests for ClaudeCodeModel.request method."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.mark.asyncio
    async def test_successful_request(self, mock_result_message: ResultMessage) -> None:
        """request should return ModelResponse on success."""
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
            assert response.parts[0].content == "Response from Claude"

    @pytest.mark.asyncio
    async def test_passes_system_prompt_to_cli(
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
    async def test_uses_timeout_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use timeout from model_settings for SDK query."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"timeout": 60.0}

        # Capture the timeout used by mocking _execute_sdk_query
        captured_timeouts: list[float] = []

        async def mock_execute_sdk_query(
            prompt: str, options: ClaudeAgentOptions, timeout: float
        ) -> ResultMessage:
            captured_timeouts.append(timeout)
            return mock_result_message

        with patch.object(model, "_execute_sdk_query", mock_execute_sdk_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_timeouts) == 1
            assert captured_timeouts[0] == 60.0

    @pytest.mark.asyncio
    async def test_creates_new_cli_per_request(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should call SDK query for each request."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        query_call_count = 0

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            nonlocal query_call_count
            query_call_count += 1
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            # Make two requests
            await model.request(messages, None, params)
            await model.request(messages, None, params)

            # Should have called query twice
            assert query_call_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_empty_prompt(self) -> None:
        """request should raise ValueError when no user prompt found."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="System")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        with pytest.raises(ValueError, match="No user prompt found"):
            await model.request(messages, None, params)

    @pytest.mark.asyncio
    async def test_uses_max_budget_usd_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use max_budget_usd from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_budget_usd": 1.5}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].max_budget_usd == 1.5

    @pytest.mark.asyncio
    async def test_uses_append_system_prompt_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use append_system_prompt from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"append_system_prompt": "Be concise."}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].system_prompt == "Be concise."

    @pytest.mark.asyncio
    async def test_uses_all_new_options_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use all new options from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {
            "timeout": 60.0,
            "max_budget_usd": 2.0,
            "append_system_prompt": "Keep it brief.",
        }

        captured_options: list[ClaudeAgentOptions] = []
        captured_timeouts: list[float] = []

        async def mock_execute_sdk_query(
            prompt: str, options: ClaudeAgentOptions, timeout: float
        ) -> ResultMessage:
            captured_options.append(options)
            captured_timeouts.append(timeout)
            return mock_result_message

        with patch.object(model, "_execute_sdk_query", mock_execute_sdk_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_timeouts[0] == 60.0
            assert captured_options[0].max_budget_usd == 2.0
            assert captured_options[0].system_prompt == "Keep it brief."

    @pytest.mark.asyncio
    async def test_rejects_negative_max_budget_usd_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should raise ValueError for negative max_budget_usd."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_budget_usd": -1.0}

        with pytest.raises(ValueError, match="max_budget_usd must be non-negative"):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_converts_integer_max_budget_usd_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should convert integer max_budget_usd to float."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_budget_usd": 5}  # integer

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].max_budget_usd == 5.0

    @pytest.mark.asyncio
    async def test_accepts_empty_string_append_system_prompt_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should accept empty string append_system_prompt."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"append_system_prompt": ""}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            # Empty string append_system_prompt should result in None system_prompt
            assert captured_options[0].system_prompt is None

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_max_budget_usd(
        self, mock_result_message: ResultMessage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """request should warn when max_budget_usd has invalid type."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_budget_usd": "1.5"}  # string instead of float

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "max_budget_usd" in caplog.text
            assert "expected int or float" in caplog.text
            assert len(captured_options) == 1
            assert captured_options[0].max_budget_usd is None

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_timeout(
        self, mock_result_message: ResultMessage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """request should warn when timeout has invalid type."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"timeout": "60"}  # string instead of float

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "timeout" in caplog.text
            assert "expected int or float" in caplog.text

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_append_system_prompt(
        self, mock_result_message: ResultMessage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """request should warn when append_system_prompt has invalid type."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"append_system_prompt": 123}  # int instead of string

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "append_system_prompt" in caplog.text
            assert "expected str" in caplog.text
            assert len(captured_options) == 1
            # Invalid append_system_prompt should be ignored
            assert captured_options[0].system_prompt is None

    @pytest.mark.asyncio
    async def test_uses_max_turns_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use max_turns from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_turns": 5}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].max_turns == 5

    @pytest.mark.asyncio
    async def test_rejects_non_positive_max_turns_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should raise ValueError for non-positive max_turns."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_turns": 0}

        with pytest.raises(ValueError, match="max_turns must be a positive integer"):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_max_turns(
        self, mock_result_message: ResultMessage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """request should warn when max_turns has invalid type."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_turns": "5"}  # string instead of int

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "max_turns" in caplog.text
            assert "expected int" in caplog.text
            assert len(captured_options) == 1
            assert captured_options[0].max_turns is None

    @pytest.mark.asyncio
    async def test_uses_max_turns_from_init(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use max_turns from __init__ when model_settings not provided."""
        model = ClaudeCodeModel(max_turns=3)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
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
            assert captured_options[0].max_turns == 3

    @pytest.mark.asyncio
    async def test_model_settings_max_turns_overrides_init(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should prefer max_turns from model_settings over __init__."""
        model = ClaudeCodeModel(max_turns=3)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"max_turns": 10}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].max_turns == 10


class TestClaudeCodeModelRequestWithMetadata:
    """Tests for ClaudeCodeModel.request_with_metadata method."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage with full metadata."""
        return create_mock_result_message(
            result="Response with metadata",
            subtype="success",
            duration_ms=1500,
            duration_api_ms=1200,
            num_turns=3,
            session_id="test-session-123",
            total_cost_usd=0.05,
            usage={
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_creation_input_tokens": 50,
                "cache_read_input_tokens": 25,
            },
        )

    @pytest.mark.asyncio
    async def test_request_with_metadata_returns_named_tuple(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request_with_metadata should return RequestWithMetadataResult NamedTuple."""
        from claudecode_model.types import RequestWithMetadataResult

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

            assert isinstance(result, RequestWithMetadataResult)
            assert hasattr(result, "response")
            assert hasattr(result, "cli_response")

    @pytest.mark.asyncio
    async def test_request_with_metadata_response_matches_request(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request_with_metadata response should match regular request output."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

            assert isinstance(result.response, ModelResponse)
            assert len(result.response.parts) == 1
            assert isinstance(result.response.parts[0], TextPart)
            assert result.response.parts[0].content == "Response with metadata"
            assert result.response.model_name == model.model_name

    @pytest.mark.asyncio
    async def test_request_with_metadata_preserves_all_cli_fields(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request_with_metadata should preserve all CLI metadata fields."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

            # Verify all metadata fields are preserved
            assert result.cli_response.type == "result"
            assert result.cli_response.subtype == "success"
            assert result.cli_response.is_error is False
            assert result.cli_response.duration_ms == 1500
            assert result.cli_response.duration_api_ms == 1200
            assert result.cli_response.num_turns == 3
            assert result.cli_response.result == "Response with metadata"
            assert result.cli_response.session_id == "test-session-123"
            assert result.cli_response.total_cost_usd == 0.05
            assert result.cli_response.usage.input_tokens == 200
            assert result.cli_response.usage.output_tokens == 100
            assert result.cli_response.usage.cache_creation_input_tokens == 50
            assert result.cli_response.usage.cache_read_input_tokens == 25

    @pytest.mark.asyncio
    async def test_request_with_metadata_with_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request_with_metadata should pass model_settings to SDK options."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {
            "timeout": 120.0,
            "max_budget_usd": 1.0,
            "max_turns": 5,
        }

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request_with_metadata(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].max_budget_usd == 1.0
            assert captured_options[0].max_turns == 5

    @pytest.mark.asyncio
    async def test_request_with_metadata_raises_on_error(self) -> None:
        """request_with_metadata should raise ValueError when no user prompt found."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="System")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        with pytest.raises(ValueError, match="No user prompt found"):
            await model.request_with_metadata(messages, None, params)


class TestClaudeCodeModelWorkingDirectoryOverride:
    """Tests for working_directory override via model_settings."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.mark.asyncio
    async def test_uses_working_directory_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use working_directory from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"working_directory": "/custom/path"}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].cwd == "/custom/path"

    @pytest.mark.asyncio
    async def test_model_settings_working_directory_overrides_init(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should prefer working_directory from model_settings over __init__."""
        model = ClaudeCodeModel(working_directory="/init/path")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"working_directory": "/override/path"}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].cwd == "/override/path"

    @pytest.mark.asyncio
    async def test_uses_init_working_directory_when_not_in_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use working_directory from __init__ when not in model_settings."""
        model = ClaudeCodeModel(working_directory="/init/path")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
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
            assert captured_options[0].cwd == "/init/path"

    @pytest.mark.asyncio
    async def test_raises_on_invalid_type_working_directory(self) -> None:
        """request should raise TypeError when working_directory has invalid type."""
        model = ClaudeCodeModel(working_directory="/init/path")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"working_directory": 123}  # int instead of string

        with pytest.raises(TypeError, match="working_directory.*must be str.*got int"):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_working_directory_none_in_model_settings_uses_init(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use init value when model_settings working_directory is None."""
        model = ClaudeCodeModel(working_directory="/init/path")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"working_directory": None}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].cwd == "/init/path"

    @pytest.mark.asyncio
    async def test_warns_on_empty_string_working_directory(
        self, mock_result_message: ResultMessage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """request should warn when working_directory is empty string."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"working_directory": ""}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "working_directory" in caplog.text
            assert "empty string" in caplog.text
            assert len(captured_options) == 1
            assert captured_options[0].cwd == ""


class TestRequestFunctionToolsProcessing:
    """Tests for request() processing model_request_parameters.function_tools."""

    @pytest.mark.asyncio
    async def test_request_uses_function_tools_with_registered_toolsets(self) -> None:
        """request should use function_tools to filter registered toolsets."""

        async def weather_func(city: str) -> str:
            return f"Weather in {city}"

        async def search_func(query: str) -> str:
            return f"Search: {query}"

        # Create mock toolset with tools dict (like _AgentFunctionToolset)
        mock_toolset = MagicMock()
        mock_weather_tool = MagicMock()
        mock_weather_tool.name = "get_weather"
        mock_weather_tool.description = "Get weather"
        mock_weather_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"city": {"type": "string"}},
        }
        mock_weather_tool.function = weather_func

        mock_search_tool = MagicMock()
        mock_search_tool.name = "search"
        mock_search_tool.description = "Search"
        mock_search_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }
        mock_search_tool.function = search_func

        mock_toolset.tools = {
            "get_weather": mock_weather_tool,
            "search": mock_search_tool,
        }

        model = ClaudeCodeModel()
        model.set_agent_toolsets(mock_toolset)

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="What's the weather?")])
        ]

        # Only request get_weather tool via function_tools
        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="get_weather",
                    description="Get weather",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                )
            ],
            allow_text_output=True,
        )

        mock_result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Weather response",
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        # MCP server should be created with matched tools
        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers is not None
        assert isinstance(captured_options[0].mcp_servers, dict)
        assert "pydantic_tools" in captured_options[0].mcp_servers

    @pytest.mark.asyncio
    async def test_request_raises_tool_not_found_error_with_empty_toolset(self) -> None:
        """request should raise ToolNotFoundError when function_tools not found in registered toolsets."""
        # Create empty toolset
        model = ClaudeCodeModel()
        model.set_agent_toolsets([])

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        # Request a tool that doesn't exist
        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="nonexistent_tool",
                    description="Does not exist",
                    parameters_json_schema={"type": "object", "properties": {}},
                )
            ],
            allow_text_output=True,
        )

        with pytest.raises(ToolNotFoundError) as exc_info:
            await model.request(messages, None, params)

        assert "nonexistent_tool" in str(exc_info.value)
        assert exc_info.value.missing_tools == ["nonexistent_tool"]
        assert exc_info.value.available_tools == []

    @pytest.mark.asyncio
    async def test_request_ignores_empty_function_tools(self) -> None:
        """request should not modify MCP servers when function_tools is empty."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        # Register a tool
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model = ClaudeCodeModel()
        model.set_agent_toolsets([mock_tool])

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        # Empty function_tools
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        mock_result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        # MCP servers should still contain registered tools
        assert len(captured_options) == 1
        assert isinstance(captured_options[0].mcp_servers, dict)
        assert "pydantic_tools" in captured_options[0].mcp_servers

    @pytest.mark.asyncio
    async def test_request_raises_toolset_not_registered_error(self) -> None:
        """request should raise ToolsetNotRegisteredError when function_tools provided but no toolsets registered."""
        model = ClaudeCodeModel()
        # No toolsets registered

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="some_tool",
                    description="Some tool",
                    parameters_json_schema={"type": "object", "properties": {}},
                )
            ],
            allow_text_output=True,
        )

        with pytest.raises(ToolsetNotRegisteredError) as exc_info:
            await model.request(messages, None, params)

        assert "some_tool" in str(exc_info.value)
        assert "set_agent_toolsets" in str(exc_info.value)
        assert exc_info.value.requested_tools == ["some_tool"]

    @pytest.mark.asyncio
    async def test_request_raises_tool_not_found_error(self) -> None:
        """request should raise ToolNotFoundError when function_tools not found in registered toolsets."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        # Register a tool
        mock_tool = MagicMock()
        mock_tool.name = "existing_tool"
        mock_tool.description = "Test"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model = ClaudeCodeModel()
        model.set_agent_toolsets([mock_tool])

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        # Request a tool that doesn't exist
        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="nonexistent_tool",
                    description="Does not exist",
                    parameters_json_schema={"type": "object", "properties": {}},
                )
            ],
            allow_text_output=True,
        )

        with pytest.raises(ToolNotFoundError) as exc_info:
            await model.request(messages, None, params)

        assert "nonexistent_tool" in str(exc_info.value)
        assert "existing_tool" in str(exc_info.value)
        assert exc_info.value.missing_tools == ["nonexistent_tool"]
        assert exc_info.value.available_tools == ["existing_tool"]

    @pytest.mark.asyncio
    async def test_request_with_metadata_processes_function_tools(self) -> None:
        """request_with_metadata should process function_tools like request does."""

        async def weather_func(city: str) -> str:
            return f"Weather in {city}"

        # Create mock toolset with tools dict
        mock_toolset = MagicMock()
        mock_weather_tool = MagicMock()
        mock_weather_tool.name = "get_weather"
        mock_weather_tool.description = "Get weather"
        mock_weather_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"city": {"type": "string"}},
        }
        mock_weather_tool.function = weather_func

        mock_toolset.tools = {"get_weather": mock_weather_tool}

        model = ClaudeCodeModel()
        model.set_agent_toolsets(mock_toolset)

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="What's the weather?")])
        ]

        # Request get_weather tool via function_tools
        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="get_weather",
                    description="Get weather",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                )
            ],
            allow_text_output=True,
        )

        mock_result = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Weather response",
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

        # Should return RequestWithMetadataResult
        assert result.response is not None
        assert result.cli_response is not None

        # MCP server should be created with matched tools
        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers is not None
        assert isinstance(captured_options[0].mcp_servers, dict)
        assert "pydantic_tools" in captured_options[0].mcp_servers

    @pytest.mark.asyncio
    async def test_request_with_metadata_raises_toolset_not_registered_error(
        self,
    ) -> None:
        """request_with_metadata should raise ToolsetNotRegisteredError when function_tools provided but no toolsets registered."""
        model = ClaudeCodeModel()
        # No toolsets registered

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="some_tool",
                    description="Some tool",
                    parameters_json_schema={"type": "object", "properties": {}},
                )
            ],
            allow_text_output=True,
        )

        with pytest.raises(ToolsetNotRegisteredError) as exc_info:
            await model.request_with_metadata(messages, None, params)

        assert "some_tool" in str(exc_info.value)
        assert exc_info.value.requested_tools == ["some_tool"]

    def test_set_agent_toolsets_with_agent_toolset_object(self) -> None:
        """set_agent_toolsets should handle AgentToolset objects correctly."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        # Create mock AgentToolset (like _AgentFunctionToolset)
        mock_toolset = MagicMock()
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Tool 1"
        mock_tool1.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool1.function = dummy_func

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Tool 2"
        mock_tool2.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool2.function = dummy_func

        mock_toolset.tools = {"tool1": mock_tool1, "tool2": mock_tool2}

        model = ClaudeCodeModel()
        model.set_agent_toolsets(mock_toolset)

        # Verify tools cache is built correctly
        assert "tool1" in model._tools_cache
        assert "tool2" in model._tools_cache
        assert model._tools_cache["tool1"] == mock_tool1
        assert model._tools_cache["tool2"] == mock_tool2

        # Verify available tool names
        available = model._get_available_tool_names()
        assert set(available) == {"tool1", "tool2"}

    def test_find_tools_by_names_uses_cache(self) -> None:
        """_find_tools_by_names should use pre-built cache for O(1) lookup."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Tool 1"
        mock_tool1.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool1.function = dummy_func

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Tool 2"
        mock_tool2.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool2.function = dummy_func

        model = ClaudeCodeModel()
        model.set_agent_toolsets([mock_tool1, mock_tool2])

        # Find existing tool
        found, missing = model._find_tools_by_names(["tool1"])
        assert len(found) == 1
        assert found[0] == mock_tool1
        assert missing == []

        # Find multiple tools with some missing
        found, missing = model._find_tools_by_names(["tool1", "tool3", "tool2"])
        assert len(found) == 2
        assert mock_tool1 in found
        assert mock_tool2 in found
        assert missing == ["tool3"]

    def test_get_available_tool_names(self) -> None:
        """_get_available_tool_names should return list of tool names from cache."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model = ClaudeCodeModel()
        model.set_agent_toolsets([mock_tool])

        names = model._get_available_tool_names()
        assert names == ["test_tool"]

    def test_tools_cache_cleared_on_set_agent_toolsets(self) -> None:
        """set_agent_toolsets should clear and rebuild tools cache."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        # First set of tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Tool 1"
        mock_tool1.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool1.function = dummy_func

        model = ClaudeCodeModel()
        model.set_agent_toolsets([mock_tool1])
        assert "tool1" in model._tools_cache

        # Second set of tools (different)
        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Tool 2"
        mock_tool2.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool2.function = dummy_func

        model.set_agent_toolsets([mock_tool2])
        assert "tool1" not in model._tools_cache
        assert "tool2" in model._tools_cache
