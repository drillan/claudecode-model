"""Tests for claudecode_model.model module."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
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
from claudecode_model.types import CLIResponse, CLIUsage


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
    def mock_cli_response(self) -> CLIResponse:
        """Return a mock CLI response."""
        return CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            result="Response from Claude",
            usage=CLIUsage(
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )

    @pytest.mark.asyncio
    async def test_successful_request(self, mock_cli_response: CLIResponse) -> None:
        """request should return ModelResponse on success."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        with (
            patch.object(ClaudeCodeModel, "_extract_user_prompt", return_value="Hello"),
            patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class,
        ):
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            response = await model.request(messages, None, params)

            assert isinstance(response, ModelResponse)
            assert len(response.parts) == 1
            assert isinstance(response.parts[0], TextPart)
            assert response.parts[0].content == "Response from Claude"

    @pytest.mark.asyncio
    async def test_passes_system_prompt_to_cli(
        self, mock_cli_response: CLIResponse
    ) -> None:
        """request should pass system prompt to CLI."""
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, None, params)

            mock_cli_class.assert_called_once()
            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["system_prompt"] == "Be helpful"

    @pytest.mark.asyncio
    async def test_uses_timeout_from_model_settings(
        self, mock_cli_response: CLIResponse
    ) -> None:
        """request should use timeout from model_settings if provided."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"timeout": 60.0}

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["timeout"] == 60.0

    @pytest.mark.asyncio
    async def test_creates_new_cli_per_request(
        self, mock_cli_response: CLIResponse
    ) -> None:
        """request should create new CLI instance per request (no race condition)."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            # Make two requests
            await model.request(messages, None, params)
            await model.request(messages, None, params)

            # Should have created two CLI instances
            assert mock_cli_class.call_count == 2

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
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_budget_usd"] == 1.5

    @pytest.mark.asyncio
    async def test_uses_append_system_prompt_from_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["append_system_prompt"] == "Be concise."

    @pytest.mark.asyncio
    async def test_uses_all_new_options_from_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["timeout"] == 60.0
            assert call_kwargs["max_budget_usd"] == 2.0
            assert call_kwargs["append_system_prompt"] == "Keep it brief."

    @pytest.mark.asyncio
    async def test_rejects_negative_max_budget_usd_from_model_settings(
        self, mock_cli_response: CLIResponse
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
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_budget_usd"] == 5.0

    @pytest.mark.asyncio
    async def test_accepts_empty_string_append_system_prompt_from_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["append_system_prompt"] == ""

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_max_budget_usd(
        self, mock_cli_response: CLIResponse, caplog: pytest.LogCaptureFixture
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "max_budget_usd" in caplog.text
            assert "expected int or float" in caplog.text
            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_budget_usd"] is None

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_timeout(
        self, mock_cli_response: CLIResponse, caplog: pytest.LogCaptureFixture
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "timeout" in caplog.text
            assert "expected int or float" in caplog.text

    @pytest.mark.asyncio
    async def test_warns_on_invalid_type_append_system_prompt(
        self, mock_cli_response: CLIResponse, caplog: pytest.LogCaptureFixture
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "append_system_prompt" in caplog.text
            assert "expected str" in caplog.text
            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["append_system_prompt"] is None

    @pytest.mark.asyncio
    async def test_uses_max_turns_from_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_turns"] == 5

    @pytest.mark.asyncio
    async def test_rejects_non_positive_max_turns_from_model_settings(
        self, mock_cli_response: CLIResponse
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
        self, mock_cli_response: CLIResponse, caplog: pytest.LogCaptureFixture
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "max_turns" in caplog.text
            assert "expected int" in caplog.text
            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_turns"] is None

    @pytest.mark.asyncio
    async def test_uses_max_turns_from_init(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, None, params)

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_turns"] == 3

    @pytest.mark.asyncio
    async def test_model_settings_max_turns_overrides_init(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["max_turns"] == 10


class TestClaudeCodeModelRequestWithMetadata:
    """Tests for ClaudeCodeModel.request_with_metadata method."""

    @pytest.fixture
    def mock_cli_response(self) -> CLIResponse:
        """Return a mock CLI response with full metadata."""
        return CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1500,
            duration_api_ms=1200,
            num_turns=3,
            result="Response with metadata",
            session_id="test-session-123",
            total_cost_usd=0.05,
            usage=CLIUsage(
                input_tokens=200,
                output_tokens=100,
                cache_creation_input_tokens=50,
                cache_read_input_tokens=25,
            ),
        )

    @pytest.mark.asyncio
    async def test_request_with_metadata_returns_named_tuple(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            result = await model.request_with_metadata(messages, None, params)

            assert isinstance(result, RequestWithMetadataResult)
            assert hasattr(result, "response")
            assert hasattr(result, "cli_response")

    @pytest.mark.asyncio
    async def test_request_with_metadata_response_matches_request(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            result = await model.request_with_metadata(messages, None, params)

            assert isinstance(result.response, ModelResponse)
            assert len(result.response.parts) == 1
            assert isinstance(result.response.parts[0], TextPart)
            assert result.response.parts[0].content == "Response with metadata"
            assert result.response.model_name == model.model_name

    @pytest.mark.asyncio
    async def test_request_with_metadata_preserves_all_cli_fields(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

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
        self, mock_cli_response: CLIResponse
    ) -> None:
        """request_with_metadata should pass model_settings to CLI."""
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request_with_metadata(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["timeout"] == 120.0
            assert call_kwargs["max_budget_usd"] == 1.0
            assert call_kwargs["max_turns"] == 5

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
    def mock_cli_response(self) -> CLIResponse:
        """Return a mock CLI response."""
        return CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            result="Response from Claude",
            usage=CLIUsage(
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )

    @pytest.mark.asyncio
    async def test_uses_working_directory_from_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["working_directory"] == "/custom/path"

    @pytest.mark.asyncio
    async def test_model_settings_working_directory_overrides_init(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["working_directory"] == "/override/path"

    @pytest.mark.asyncio
    async def test_uses_init_working_directory_when_not_in_model_settings(
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, None, params)

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["working_directory"] == "/init/path"

    @pytest.mark.asyncio
    async def test_raises_on_invalid_type_working_directory(
        self, mock_cli_response: CLIResponse
    ) -> None:
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
        self, mock_cli_response: CLIResponse
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            await model.request(messages, settings, params)  # type: ignore[arg-type]

            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["working_directory"] == "/init/path"

    @pytest.mark.asyncio
    async def test_warns_on_empty_string_working_directory(
        self, mock_cli_response: CLIResponse, caplog: pytest.LogCaptureFixture
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

        with patch("claudecode_model.model.ClaudeCodeCLI") as mock_cli_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.execute = AsyncMock(return_value=mock_cli_response)

            with caplog.at_level(logging.WARNING):
                await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert "working_directory" in caplog.text
            assert "empty string" in caplog.text
            call_kwargs = mock_cli_class.call_args.kwargs
            assert call_kwargs["working_directory"] == ""
