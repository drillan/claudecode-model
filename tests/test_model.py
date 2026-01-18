"""Tests for claudecode_model.model module."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import patch

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

from claudecode_model.cli import DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS
from claudecode_model.model import ClaudeCodeModel


def create_mock_result_message(
    result: str = "Response from Claude",
    is_error: bool = False,
    subtype: str = "success",
    duration_ms: int = 1000,
    duration_api_ms: int = 800,
    num_turns: int = 1,
    session_id: str = "test-session",
    total_cost_usd: float | None = None,
    usage: dict[str, int] | None = None,
    structured_output: dict[str, object] | None = None,
) -> ResultMessage:
    """Create a mock ResultMessage for testing."""
    return ResultMessage(
        subtype=subtype,
        duration_ms=duration_ms,
        duration_api_ms=duration_api_ms,
        is_error=is_error,
        num_turns=num_turns,
        session_id=session_id,
        result=result,
        total_cost_usd=total_cost_usd,
        usage=usage
        or {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        structured_output=structured_output,
    )


class TestClaudeCodeModelInit:
    """Tests for ClaudeCodeModel initialization."""

    def test_default_values(self) -> None:
        """ClaudeCodeModel should use default values."""
        model = ClaudeCodeModel()
        assert model.model_name == DEFAULT_MODEL
        assert model._timeout == DEFAULT_TIMEOUT_SECONDS
        assert model._working_directory is None
        assert model._allowed_tools is None
        assert model._disallowed_tools is None
        assert model._permission_mode is None

    def test_custom_values(self) -> None:
        """ClaudeCodeModel should accept custom values."""
        model = ClaudeCodeModel(
            model_name="claude-opus-4",
            working_directory="/tmp",
            timeout=60.0,
            allowed_tools=["Read"],
            disallowed_tools=["Bash"],
            permission_mode="bypassPermissions",
        )
        assert model.model_name == "claude-opus-4"
        assert model._working_directory == "/tmp"
        assert model._timeout == 60.0
        assert model._allowed_tools == ["Read"]
        assert model._disallowed_tools == ["Bash"]
        assert model._permission_mode == "bypassPermissions"

    def test_max_turns_default_to_none(self) -> None:
        """ClaudeCodeModel max_turns should default to None."""
        model = ClaudeCodeModel()
        assert model._max_turns is None

    def test_max_turns_accepts_positive_value(self) -> None:
        """ClaudeCodeModel should accept positive max_turns."""
        model = ClaudeCodeModel(max_turns=5)
        assert model._max_turns == 5


class TestClaudeCodeModelProperties:
    """Tests for ClaudeCodeModel properties."""

    def test_model_name_property(self) -> None:
        """model_name property should return the model name."""
        model = ClaudeCodeModel(model_name="test-model")
        assert model.model_name == "test-model"

    def test_system_property(self) -> None:
        """system property should return 'claude-code'."""
        model = ClaudeCodeModel()
        assert model.system == "claude-code"


class TestClaudeCodeModelProfile:
    """Tests for ClaudeCodeModel profile configuration."""

    def test_profile_supports_json_schema_output(self) -> None:
        """ClaudeCodeModel profile should support JSON schema output."""
        model = ClaudeCodeModel()
        assert model.profile.supports_json_schema_output is True

    def test_profile_default_structured_output_mode_is_native(self) -> None:
        """ClaudeCodeModel profile should default to native output mode."""
        model = ClaudeCodeModel()
        assert model.profile.default_structured_output_mode == "native"

    def test_profile_is_cached(self) -> None:
        """ClaudeCodeModel profile should be cached (same instance)."""
        model = ClaudeCodeModel()
        profile1 = model.profile
        profile2 = model.profile
        assert profile1 is profile2


class TestClaudeCodeModelRepr:
    """Tests for ClaudeCodeModel __repr__."""

    def test_repr(self) -> None:
        """__repr__ should return a readable representation."""
        model = ClaudeCodeModel(model_name="test-model")
        assert repr(model) == "ClaudeCodeModel(model_name='test-model')"


class TestClaudeCodeModelExtractSystemPrompt:
    """Tests for ClaudeCodeModel._extract_system_prompt method."""

    def test_extracts_system_prompt(self) -> None:
        """_extract_system_prompt should extract system prompt from messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="You are helpful."),
                    UserPromptPart(content="Hello"),
                ]
            )
        ]
        result = model._extract_system_prompt(messages)
        assert result == "You are helpful."

    def test_returns_none_when_no_system_prompt(self) -> None:
        """_extract_system_prompt should return None when no system prompt."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        result = model._extract_system_prompt(messages)
        assert result is None

    def test_returns_first_system_prompt(self) -> None:
        """_extract_system_prompt should return the first system prompt found."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="First"),
                    SystemPromptPart(content="Second"),
                ]
            )
        ]
        result = model._extract_system_prompt(messages)
        assert result == "First"


class TestClaudeCodeModelExtractUserPrompt:
    """Tests for ClaudeCodeModel._extract_user_prompt method."""

    def test_extracts_user_prompt(self) -> None:
        """_extract_user_prompt should extract user prompt from messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Hello"

    def test_joins_multiple_user_prompts(self) -> None:
        """_extract_user_prompt should join multiple user prompts."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    UserPromptPart(content="Hello"),
                    UserPromptPart(content="World"),
                ]
            )
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Hello\nWorld"

    def test_raises_on_empty_messages(self) -> None:
        """_extract_user_prompt should raise ValueError on empty messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = []
        with pytest.raises(ValueError, match="No user prompt found"):
            model._extract_user_prompt(messages)

    def test_raises_on_no_user_prompt(self) -> None:
        """_extract_user_prompt should raise ValueError when no user prompt."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="System")])
        ]
        with pytest.raises(ValueError, match="No user prompt found"):
            model._extract_user_prompt(messages)

    def test_handles_list_content(self) -> None:
        """_extract_user_prompt should handle list content."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    UserPromptPart(content=["Part 1", "Part 2"]),  # type: ignore[arg-type]
                ]
            )
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Part 1\nPart 2"


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


class TestClaudeCodeModelStructuredOutput:
    """Tests for ClaudeCodeModel structured output (output_type) support."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.fixture
    def mock_result_message_with_structured_output(self) -> ResultMessage:
        """Return a mock ResultMessage with structured_output."""
        return create_mock_result_message(
            result="Generated output",
            structured_output={"name": "test", "score": 95},
        )

    @pytest.mark.asyncio
    async def test_request_without_output_mode_does_not_pass_json_schema(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should not pass json_schema when output_mode is not native."""
        model = ClaudeCodeModel()
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
            assert captured_options[0].output_format is None

    @pytest.mark.asyncio
    async def test_request_with_native_output_mode_passes_json_schema(
        self, mock_result_message_with_structured_output: ResultMessage
    ) -> None:
        """request should pass json_schema when output_mode is native."""
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["name", "score"],
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
            yield mock_result_message_with_structured_output

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

            assert len(captured_options) == 1
            assert captured_options[0].output_format == {
                "type": "json_schema",
                "schema": json_schema,
            }

    @pytest.mark.asyncio
    async def test_request_with_native_output_mode_without_output_object(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should not pass json_schema when output_mode is native but no output_object."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="native",
            output_object=None,
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
            assert captured_options[0].output_format is None

    @pytest.mark.asyncio
    async def test_request_with_tool_output_mode_does_not_pass_json_schema(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should not pass json_schema when output_mode is tool."""
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="tool",
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

            # Should NOT pass json_schema for tool mode
            assert len(captured_options) == 1
            assert captured_options[0].output_format is None

    @pytest.mark.asyncio
    async def test_request_with_structured_output_returns_json_in_response(
        self, mock_result_message_with_structured_output: ResultMessage
    ) -> None:
        """request should return JSON string in response when structured_output present."""
        from pydantic_ai.models import OutputObjectDefinition
        import json

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "integer"},
            },
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

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield mock_result_message_with_structured_output

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            # The response content should be JSON string
            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test", "score": 95}

    @pytest.mark.asyncio
    async def test_request_with_metadata_preserves_structured_output(
        self, mock_result_message_with_structured_output: ResultMessage
    ) -> None:
        """request_with_metadata should preserve structured_output in cli_response."""
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
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

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield mock_result_message_with_structured_output

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

            assert result.cli_response.structured_output is not None
            assert result.cli_response.structured_output["name"] == "test"
            assert result.cli_response.structured_output["score"] == 95

    @pytest.mark.asyncio
    async def test_agent_with_output_type_auto_generates_json_schema(
        self, mock_result_message_with_structured_output: ResultMessage
    ) -> None:
        """Agent with output_type should automatically use --json-schema.

        This test verifies that the profile settings enable automatic JSON schema
        generation when pydantic-ai Agent uses output_type.
        """
        from pydantic import BaseModel
        from pydantic_ai.models import OutputObjectDefinition

        class Evaluation(BaseModel):
            score: int
            comment: str

        model = ClaudeCodeModel()

        # Verify profile settings enable auto JSON schema
        assert model.profile.supports_json_schema_output is True
        assert model.profile.default_structured_output_mode == "native"

        # Create parameters simulating what Agent would create with output_type
        json_schema = Evaluation.model_json_schema()
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="native",
            output_object=OutputObjectDefinition(
                json_schema=json_schema,
                name="Evaluation",
                description="Evaluation output",
                strict=True,
            ),
        )

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Rate this code")])
        ]

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message_with_structured_output

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

            # Verify json_schema is passed via output_format
            assert len(captured_options) == 1
            assert captured_options[0].output_format == {
                "type": "json_schema",
                "schema": json_schema,
            }


class TestClaudeCodeModelExtractJsonSchema:
    """Tests for ClaudeCodeModel._extract_json_schema method."""

    def test_extract_json_schema_with_native_mode_returns_schema(self) -> None:
        """_extract_json_schema should return schema when output_mode is native."""
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        json_schema = {"type": "object", "properties": {"name": {"type": "string"}}}

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

        result = model._extract_json_schema(params)
        assert result == json_schema

    def test_extract_json_schema_with_native_mode_no_output_object_returns_none(
        self,
    ) -> None:
        """_extract_json_schema should return None when output_mode is native but no output_object."""
        model = ClaudeCodeModel()

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="native",
            output_object=None,
        )

        result = model._extract_json_schema(params)
        assert result is None

    def test_extract_json_schema_with_tool_mode_returns_none(self) -> None:
        """_extract_json_schema should return None when output_mode is tool."""
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        json_schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="tool",
            output_object=OutputObjectDefinition(
                json_schema=json_schema,
                name="TestOutput",
                description="Test output",
                strict=True,
            ),
        )

        result = model._extract_json_schema(params)
        assert result is None

    def test_extract_json_schema_with_auto_mode_uses_profile_default(self) -> None:
        """_extract_json_schema should use profile default when output_mode is auto.

        When pydantic-ai Agent sets output_type, it calls with output_mode='auto'.
        The model should resolve 'auto' to profile.default_structured_output_mode.
        """
        from pydantic_ai.models import OutputObjectDefinition

        model = ClaudeCodeModel()
        # Verify profile default is 'native'
        assert model.profile.default_structured_output_mode == "native"

        json_schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="auto",
            output_object=OutputObjectDefinition(
                json_schema=json_schema,
                name="TestOutput",
                description="Test output",
                strict=True,
            ),
        )

        result = model._extract_json_schema(params)
        # Should return schema because auto resolves to native
        assert result == json_schema

    def test_extract_json_schema_with_auto_mode_no_output_object_returns_none(
        self,
    ) -> None:
        """_extract_json_schema should return None when output_mode is auto but no output_object."""
        model = ClaudeCodeModel()

        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
            output_mode="auto",
            output_object=None,
        )

        result = model._extract_json_schema(params)
        assert result is None


class TestClaudeCodeModelBuildAgentOptions:
    """Tests for ClaudeCodeModel._build_agent_options method."""

    def test_build_agent_options_default_values(self) -> None:
        """_build_agent_options should use default model values."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel()
        options = model._build_agent_options()

        assert isinstance(options, ClaudeAgentOptions)
        assert options.model == DEFAULT_MODEL
        assert options.cwd is None
        assert options.allowed_tools == []
        assert options.disallowed_tools == []
        assert options.permission_mode is None
        assert options.max_turns is None
        assert options.max_budget_usd is None
        assert options.system_prompt is None
        assert options.output_format is None

    def test_build_agent_options_with_custom_model_values(self) -> None:
        """_build_agent_options should use custom model values from __init__."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel(
            model_name="claude-opus-4",
            working_directory="/custom/path",
            allowed_tools=["Read", "Write"],
            disallowed_tools=["Bash"],
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        options = model._build_agent_options()

        assert isinstance(options, ClaudeAgentOptions)
        assert options.model == "claude-opus-4"
        assert options.cwd == "/custom/path"
        assert options.allowed_tools == ["Read", "Write"]
        assert options.disallowed_tools == ["Bash"]
        assert options.permission_mode == "bypassPermissions"
        assert options.max_turns == 5

    def test_build_agent_options_with_override_values(self) -> None:
        """_build_agent_options should allow override values via parameters."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel(
            model_name="claude-sonnet-4-5",
            working_directory="/default/path",
            max_turns=3,
        )
        options = model._build_agent_options(
            system_prompt="Custom prompt",
            max_budget_usd=1.5,
            max_turns=10,  # Override
            working_directory="/override/path",  # Override
        )

        assert isinstance(options, ClaudeAgentOptions)
        assert options.system_prompt == "Custom prompt"
        assert options.max_budget_usd == 1.5
        assert options.max_turns == 10
        assert options.cwd == "/override/path"

    def test_build_agent_options_with_json_schema(self) -> None:
        """_build_agent_options should convert json_schema to output_format."""
        from claude_agent_sdk import ClaudeAgentOptions

        from claudecode_model.types import JsonValue

        model = ClaudeCodeModel()
        json_schema: dict[str, JsonValue] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        options = model._build_agent_options(json_schema=json_schema)

        assert isinstance(options, ClaudeAgentOptions)
        assert options.output_format is not None
        assert options.output_format["type"] == "json_schema"
        assert options.output_format["schema"] == json_schema

    def test_build_agent_options_without_json_schema(self) -> None:
        """_build_agent_options should not set output_format when json_schema is None."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel()
        options = model._build_agent_options(json_schema=None)

        assert isinstance(options, ClaudeAgentOptions)
        assert options.output_format is None

    def test_build_agent_options_with_append_system_prompt(self) -> None:
        """_build_agent_options should combine system_prompt and append_system_prompt."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel()
        options = model._build_agent_options(
            system_prompt="Main prompt",
            append_system_prompt="Additional instructions",
        )

        assert isinstance(options, ClaudeAgentOptions)
        assert options.system_prompt == "Main prompt\n\nAdditional instructions"

    def test_build_agent_options_with_only_append_system_prompt(self) -> None:
        """_build_agent_options should use append_system_prompt alone when system_prompt is None."""
        from claude_agent_sdk import ClaudeAgentOptions

        model = ClaudeCodeModel()
        options = model._build_agent_options(
            system_prompt=None,
            append_system_prompt="Additional instructions",
        )

        assert isinstance(options, ClaudeAgentOptions)
        assert options.system_prompt == "Additional instructions"


class TestClaudeCodeModelResultMessageToCLIResponse:
    """Tests for ClaudeCodeModel._result_message_to_cli_response method."""

    def test_converts_basic_result_message(self) -> None:
        """_result_message_to_cli_response should convert basic ResultMessage."""
        from claude_agent_sdk import ResultMessage

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
        from claude_agent_sdk import ResultMessage

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
        from claude_agent_sdk import ResultMessage

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
        from claude_agent_sdk import ResultMessage

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
        from claude_agent_sdk import ResultMessage

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

    def test_converts_error_result_message(self) -> None:
        """_result_message_to_cli_response should preserve is_error flag."""
        from claude_agent_sdk import ResultMessage

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
        """_execute_sdk_query should return ResultMessage from SDK."""
        from unittest.mock import MagicMock
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

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
            result = await model._execute_sdk_query(
                "Test prompt", options, timeout=60.0
            )

        assert result is expected_result

    @pytest.mark.asyncio
    async def test_execute_sdk_query_timeout(self) -> None:
        """_execute_sdk_query should raise CLIExecutionError on timeout."""
        import anyio
        from claude_agent_sdk import ClaudeAgentOptions
        from claudecode_model.exceptions import CLIExecutionError

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
        from claude_agent_sdk import ClaudeAgentOptions, UserMessage
        from claudecode_model.exceptions import CLIExecutionError

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
    def mock_result_message(self) -> "ResultMessage":
        """Return a mock ResultMessage."""
        from claude_agent_sdk import ResultMessage

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
        self, mock_result_message: "ResultMessage"
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

        async def mock_query(**kwargs: object) -> AsyncIterator["ResultMessage"]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

        assert isinstance(response, ModelResponse)
        assert len(response.parts) == 1
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "Response from SDK"

    @pytest.mark.asyncio
    async def test_request_passes_system_prompt_to_sdk(
        self, mock_result_message: "ResultMessage"
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

        captured_options: list["ClaudeAgentOptions"] = []

        async def mock_query(
            prompt: str, options: "ClaudeAgentOptions"
        ) -> AsyncIterator["ResultMessage"]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

        assert len(captured_options) == 1
        assert captured_options[0].system_prompt == "Be helpful"

    @pytest.mark.asyncio
    async def test_request_with_model_settings(
        self, mock_result_message: "ResultMessage"
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

        captured_options: list["ClaudeAgentOptions"] = []

        async def mock_query(
            prompt: str, options: "ClaudeAgentOptions"
        ) -> AsyncIterator["ResultMessage"]:
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
        self, mock_result_message: "ResultMessage"
    ) -> None:
        """request should pass json_schema as output_format to SDK."""
        from pydantic_ai.models import OutputObjectDefinition

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

        captured_options: list["ClaudeAgentOptions"] = []

        async def mock_query(
            prompt: str, options: "ClaudeAgentOptions"
        ) -> AsyncIterator["ResultMessage"]:
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
        self, mock_result_message: "ResultMessage"
    ) -> None:
        """request_with_metadata should use SDK and preserve metadata."""
        from claudecode_model.types import RequestWithMetadataResult

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        async def mock_query(**kwargs: object) -> AsyncIterator["ResultMessage"]:
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            result = await model.request_with_metadata(messages, None, params)

        assert isinstance(result, RequestWithMetadataResult)
        assert result.cli_response.total_cost_usd == 0.05
        assert result.cli_response.num_turns == 3
        assert result.cli_response.duration_api_ms == 1200
        assert result.cli_response.session_id == "test-session-123"


class TestClaudeCodeModelIsErrorHandling:
    """Tests for is_error flag handling in _execute_request."""

    @pytest.mark.asyncio
    async def test_raises_cli_execution_error_when_is_error_true(self) -> None:
        """_execute_request should raise CLIExecutionError when is_error is True."""
        from claudecode_model.exceptions import CLIExecutionError

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
            result="SDK error message",
        )

        async def mock_query(**kwargs: object) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_request(messages, None)

        assert "SDK reported error" in str(exc_info.value)
        assert exc_info.value.error_type == "invalid_response"
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_is_error_with_none_result(self) -> None:
        """_execute_request should handle is_error=True with None result."""
        from claudecode_model.exceptions import CLIExecutionError

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

        assert "Unknown error" in str(exc_info.value)


class TestClaudeCodeModelSDKExceptionHandling:
    """Tests for SDK exception handling in _execute_sdk_query."""

    @pytest.mark.asyncio
    async def test_sdk_exception_wrapped_in_cli_execution_error(self) -> None:
        """_execute_sdk_query should wrap SDK exceptions in CLIExecutionError."""
        from claude_agent_sdk import ClaudeAgentOptions
        from claudecode_model.exceptions import CLIExecutionError

        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def mock_query_raises(**kwargs: object) -> AsyncIterator[object]:
            raise RuntimeError("SDK connection failed")
            yield  # pragma: no cover

        with patch("claudecode_model.model.query", mock_query_raises):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert "SDK query failed" in str(exc_info.value)
        assert "SDK connection failed" in str(exc_info.value)
        assert exc_info.value.error_type == "unknown"
        assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_sdk_exception_preserves_original_exception(self) -> None:
        """CLIExecutionError should chain the original SDK exception."""
        from claude_agent_sdk import ClaudeAgentOptions
        from claudecode_model.exceptions import CLIExecutionError

        model = ClaudeCodeModel()
        options = ClaudeAgentOptions()

        async def mock_query_raises(**kwargs: object) -> AsyncIterator[object]:
            raise ValueError("Invalid API key")
            yield  # pragma: no cover

        with patch("claudecode_model.model.query", mock_query_raises):
            with pytest.raises(CLIExecutionError) as exc_info:
                await model._execute_sdk_query("Test prompt", options, timeout=60.0)

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestClaudeCodeModelUsageWarning:
    """Tests for usage data warning in _result_message_to_cli_response."""

    @pytest.mark.asyncio
    async def test_logs_warning_when_usage_is_none(self, caplog: object) -> None:
        """_result_message_to_cli_response should log warning when usage is None."""
        import logging

        model = ClaudeCodeModel()

        result_no_usage = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage=None,
        )

        with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
            cli_response = model._result_message_to_cli_response(result_no_usage)

        assert "usage is None" in caplog.text  # type: ignore[attr-defined]
        assert cli_response.usage.input_tokens == 0
        assert cli_response.usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_no_warning_when_usage_present(self, caplog: object) -> None:
        """_result_message_to_cli_response should not log warning when usage exists."""
        import logging

        model = ClaudeCodeModel()

        result_with_usage = ResultMessage(
            subtype="success",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            result="Response",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
            cli_response = model._result_message_to_cli_response(result_with_usage)

        assert "usage is None" not in caplog.text  # type: ignore[attr-defined]
        assert cli_response.usage.input_tokens == 100
        assert cli_response.usage.output_tokens == 50


class TestClaudeCodeModelSetAgentToolsets:
    """Tests for ClaudeCodeModel.set_agent_toolsets method."""

    def test_set_agent_toolsets_registers_toolsets(self) -> None:
        """set_agent_toolsets should register toolsets internally."""
        from unittest.mock import MagicMock

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model.set_agent_toolsets([mock_tool])

        assert model._agent_toolsets is not None
        assert len(model._agent_toolsets) == 1

    def test_set_agent_toolsets_creates_mcp_server(self) -> None:
        """set_agent_toolsets should create MCP server from toolsets."""
        from unittest.mock import MagicMock

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
        mock_tool = MagicMock()
        mock_tool.name = "search"
        mock_tool.description = "Search documents"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model.set_agent_toolsets([mock_tool])

        assert "pydantic_tools" in model._mcp_servers

    def test_set_agent_toolsets_with_empty_list(self) -> None:
        """set_agent_toolsets should handle empty list."""
        model = ClaudeCodeModel()
        model.set_agent_toolsets([])

        assert model._agent_toolsets == []
        assert "pydantic_tools" in model._mcp_servers

    def test_set_agent_toolsets_with_none(self) -> None:
        """set_agent_toolsets should handle None."""
        model = ClaudeCodeModel()
        model.set_agent_toolsets(None)

        assert model._agent_toolsets is None
        assert "pydantic_tools" in model._mcp_servers

    def test_set_agent_toolsets_with_multiple_tools(self) -> None:
        """set_agent_toolsets should handle multiple tools."""
        from unittest.mock import MagicMock

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
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

        model.set_agent_toolsets([mock_tool1, mock_tool2])

        assert model._agent_toolsets is not None
        assert len(model._agent_toolsets) == 2

    def test_get_mcp_servers_returns_registered_servers(self) -> None:
        """get_mcp_servers should return registered MCP servers."""
        from unittest.mock import MagicMock

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
        mock_tool = MagicMock()
        mock_tool.name = "test"
        mock_tool.description = "Test"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model.set_agent_toolsets([mock_tool])

        servers = model.get_mcp_servers()
        assert "pydantic_tools" in servers

    def test_get_mcp_servers_returns_empty_dict_before_set_agent_toolsets(self) -> None:
        """get_mcp_servers should return empty dict before set_agent_toolsets."""
        model = ClaudeCodeModel()
        servers = model.get_mcp_servers()
        assert servers == {}

    def test_set_agent_toolsets_logs_warning_on_overwrite(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """set_agent_toolsets should log warning when overwriting existing toolsets."""
        import logging

        model = ClaudeCodeModel()

        # First call - no warning
        model.set_agent_toolsets([])

        # Second call - should log warning
        with caplog.at_level(logging.WARNING):
            model.set_agent_toolsets(None)

        assert "Overwriting" in caplog.text
        assert "pydantic_tools" in caplog.text
