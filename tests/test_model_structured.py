"""Tests for ClaudeCodeModel structured output functionality."""

import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters, OutputObjectDefinition

from claudecode_model.model import ClaudeCodeModel

from .conftest import create_mock_result_message


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


class TestParametersWrapperUnwrap:
    """Tests for automatic unwrapping of {"parameters": {...}} format.

    Claude Code CLI sometimes wraps structured output in a parameters envelope.
    This test class verifies that _try_unwrap_parameters_wrapper correctly
    detects and unwraps this format when appropriate.
    """

    def test_unwraps_parameters_wrapper_when_structured_output_is_none(
        self,
    ) -> None:
        """Should unwrap {"parameters": {...}} when structured_output is None."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test", "score": 95}}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped == {"name": "test", "score": 95}

    def test_does_not_unwrap_when_structured_output_is_present(self) -> None:
        """Should NOT unwrap when structured_output is already present."""
        model = ClaudeCodeModel()
        existing_output: dict[str, object] = {"existing": "value"}
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            structured_output=existing_output,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None  # Should not unwrap

    def test_does_not_unwrap_non_parameters_json(self) -> None:
        """Should NOT unwrap JSON that doesn't have 'parameters' as single key."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"name": "test", "score": 95}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_does_not_unwrap_invalid_json(self) -> None:
        """Should NOT unwrap non-JSON result strings."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result="This is not JSON",
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_does_not_unwrap_parameters_with_extra_keys(self) -> None:
        """Should NOT unwrap when there are keys besides 'parameters'."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test"}, "extra": "key"}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_does_not_unwrap_non_dict_parameters(self) -> None:
        """Should NOT unwrap when 'parameters' value is not a dict."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": ["list", "value"]}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_does_not_unwrap_empty_result(self) -> None:
        """Should NOT unwrap when result is empty."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result="",
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_warning_log_includes_session_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log warning with session_id when unwrapping."""
        import logging

        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            structured_output=None,
            session_id="test-session-123",
        )

        with caplog.at_level(logging.WARNING, logger="claudecode_model.model"):
            model._try_unwrap_parameters_wrapper(result_message)

        assert len(caplog.records) == 1
        assert "parameters" in caplog.records[0].message.lower()
        assert "test-session-123" in caplog.records[0].message
