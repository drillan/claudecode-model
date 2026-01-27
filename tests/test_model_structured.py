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

    Some models (via Claude Agent SDK) may wrap structured output in a parameters
    envelope. This test class verifies that _try_unwrap_parameters_wrapper correctly
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

    def test_does_not_unwrap_non_dict_parameter_singular(self) -> None:
        """Should NOT unwrap when 'parameter' (singular) value is not a dict."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameter": ["list", "value"]}',
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

    def test_unwraps_parameter_singular_wrapper_when_structured_output_is_none(
        self,
    ) -> None:
        """Should unwrap {"parameter": {...}} (singular) when structured_output is None."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameter": {"name": "test", "score": 95}}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped == {"name": "test", "score": 95}

    def test_info_log_includes_session_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log info with session_id when unwrapping."""
        import logging

        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            structured_output=None,
            session_id="test-session-123",
        )

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            model._try_unwrap_parameters_wrapper(result_message)

        assert len(caplog.records) == 1
        assert "parameters" in caplog.records[0].message.lower()
        assert "test-session-123" in caplog.records[0].message

    def test_info_log_includes_wrapper_key_parameters(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log info with wrapper key 'parameters' when unwrapping plural form."""
        import logging

        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            structured_output=None,
            session_id="plural-session",
        )

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            model._try_unwrap_parameters_wrapper(result_message)

        assert len(caplog.records) == 1
        assert "wrapper_key=parameters" in caplog.records[0].message

    def test_info_log_includes_wrapper_key_parameter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log info with wrapper key 'parameter' when unwrapping singular form."""
        import logging

        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"parameter": {"name": "test"}}',
            structured_output=None,
            session_id="singular-session",
        )

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            model._try_unwrap_parameters_wrapper(result_message)

        assert len(caplog.records) == 1
        assert "wrapper_key=parameter" in caplog.records[0].message

    def test_unwraps_output_wrapper_when_structured_output_is_none(
        self,
    ) -> None:
        """Should unwrap {"output": {...}} when structured_output is None."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"output": {"is_complete": false, "summary": "test"}}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped == {"is_complete": False, "summary": "test"}

    def test_does_not_unwrap_output_when_value_is_not_dict(self) -> None:
        """Should NOT unwrap when 'output' value is not a dict."""
        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"output": ["list", "value"]}',
            structured_output=None,
        )

        unwrapped = model._try_unwrap_parameters_wrapper(result_message)

        assert unwrapped is None

    def test_logs_output_wrapper_key_on_unwrap(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log info with wrapper_key=output when unwrapping output form."""
        import logging

        model = ClaudeCodeModel()
        result_message = create_mock_result_message(
            result='{"output": {"name": "test"}}',
            structured_output=None,
            session_id="output-session",
        )

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            model._try_unwrap_parameters_wrapper(result_message)

        assert len(caplog.records) == 1
        assert "wrapper_key=output" in caplog.records[0].message


class TestStructuredOutputRecovery:
    """Tests for recovery from error_max_structured_output_retries.

    When the SDK returns error_max_structured_output_retries but the result
    contains a valid {"parameters": {...}} wrapper, we should unwrap it and
    treat it as a successful response instead of raising StructuredOutputError.
    """

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_parameters_wrapper(
        self,
    ) -> None:
        """Should recover and return valid response when result has parameters wrapper."""
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

        # SDK returns error_max_structured_output_retries but with valid parameters wrapper
        error_result = create_mock_result_message(
            result='{"parameters": {"name": "test", "score": 95}}',
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            # Should NOT raise StructuredOutputError - should recover
            response = await model.request(messages, None, params)

            # Verify the response contains the unwrapped content
            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test", "score": 95}

    @pytest.mark.asyncio
    async def test_raises_error_when_no_parameters_wrapper_in_max_retries(
        self,
    ) -> None:
        """Should raise StructuredOutputError when result doesn't have parameters wrapper."""
        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        # SDK returns error without parameters wrapper
        error_result = create_mock_result_message(
            result='{"name": "test", "score": 95}',  # No parameters wrapper
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model.request(messages, None, params)

            assert "recovery failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_raises_error_when_invalid_json_in_max_retries(self) -> None:
        """Should raise StructuredOutputError when result is not valid JSON."""
        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        # SDK returns error with invalid JSON
        error_result = create_mock_result_message(
            result="This is not valid JSON",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model.request(messages, None, params)

            assert "recovery failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_raises_error_when_empty_result_in_max_retries(self) -> None:
        """Should raise StructuredOutputError when result is empty."""
        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        # SDK returns error with empty result
        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model.request(messages, None, params)

            assert "recovery failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_logs_info_on_successful_recovery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log INFO when recovery succeeds."""
        import logging

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        error_result = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            subtype="error_max_structured_output_retries",
            structured_output=None,
            session_id="recovery-session-123",
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            with patch("claudecode_model.model.query", mock_query):
                await model.request(messages, None, params)

        # Find the recovery log message
        recovery_logs = [r for r in caplog.records if "recovered" in r.message.lower()]
        assert len(recovery_logs) == 1
        assert "error_max_structured_output_retries" in recovery_logs[0].message
        assert "recovery-session-123" in recovery_logs[0].message

    @pytest.mark.asyncio
    async def test_logs_error_on_failed_recovery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log ERROR when recovery fails."""
        import logging

        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        error_result = create_mock_result_message(
            result='{"name": "test"}',  # No parameters wrapper
            subtype="error_max_structured_output_retries",
            structured_output=None,
            session_id="failed-recovery-session",
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with caplog.at_level(logging.ERROR, logger="claudecode_model.model"):
            with patch("claudecode_model.model.query", mock_query):
                with pytest.raises(StructuredOutputError):
                    await model.request(messages, None, params)

        # Find the error log message
        error_logs = [
            r for r in caplog.records if "recovery failed" in r.message.lower()
        ]
        assert len(error_logs) == 1
        assert "failed-recovery-session" in error_logs[0].message

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_parameter_singular_wrapper(
        self,
    ) -> None:
        """Should recover from error_max_retries with singular 'parameter' wrapper."""
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

        # SDK returns error_max_structured_output_retries with singular "parameter" wrapper
        error_result = create_mock_result_message(
            result='{"parameter": {"name": "test", "score": 95}}',
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            # Should NOT raise StructuredOutputError - should recover
            response = await model.request(messages, None, params)

            # Verify the response contains the unwrapped content
            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test", "score": 95}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_output_wrapper(
        self,
    ) -> None:
        """Should recover from error_max_retries with 'output' wrapper."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "is_complete": {"type": "boolean"},
                "summary": {"type": "string"},
            },
            "required": ["is_complete", "summary"],
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

        # SDK returns error_max_structured_output_retries with "output" wrapper
        error_result = create_mock_result_message(
            result='{"output": {"is_complete": false, "summary": "test"}}',
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"is_complete": False, "summary": "test"}


class TestStructuredOutputRecoveryFromCapturedInput:
    """Tests for recovery from captured ToolUseBlock input.

    When error_max_structured_output_retries occurs and ResultMessage.result is empty,
    we can still recover by extracting the structured output from the ToolUseBlock
    input captured from AssistantMessage during the query.
    """

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_captured_tool_input(
        self,
    ) -> None:
        """Should recover using captured ToolUseBlock input when result is empty."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

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

        # AssistantMessage with StructuredOutput ToolUseBlock containing the actual data
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-123",
                    name="StructuredOutput",
                    input={"parameters": {"name": "test", "score": 95}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        # ResultMessage with empty result (the typical error_max_structured_output_retries case)
        error_result = create_mock_result_message(
            result="",  # Empty result - recovery from result fails
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            # Should recover from captured ToolUseBlock input
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test", "score": 95}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_captured_tool_input_singular(
        self,
    ) -> None:
        """Should recover using captured ToolUseBlock input with singular 'parameter'."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

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

        # ToolUseBlock with singular "parameter" wrapper
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-456",
                    name="StructuredOutput",
                    input={"parameter": {"name": "test-singular"}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test-singular"}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_captured_tool_input_output_wrapper(
        self,
    ) -> None:
        """Should recover using captured ToolUseBlock input with 'output' wrapper."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {"is_complete": {"type": "boolean"}},
            "required": ["is_complete"],
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

        # ToolUseBlock with "output" wrapper
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-output-wrapper",
                    name="StructuredOutput",
                    input={"output": {"is_complete": True}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"is_complete": True}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_retries_with_captured_tool_input_no_wrapper(
        self,
    ) -> None:
        """Should recover using captured ToolUseBlock input without wrapper."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

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

        # ToolUseBlock without parameters/parameter wrapper (direct data)
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-789",
                    name="StructuredOutput",
                    input={"name": "direct-data"},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "direct-data"}

    @pytest.mark.asyncio
    async def test_raises_error_when_no_captured_tool_input(self) -> None:
        """Should raise StructuredOutputError when no ToolUseBlock was captured."""
        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        # Only ResultMessage, no AssistantMessage with ToolUseBlock
        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model.request(messages, None, params)

            assert "recovery failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_result_recovery_takes_priority_over_captured_tool_input(
        self,
    ) -> None:
        """Result-based recovery should take priority over captured ToolUseBlock."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

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

        # ToolUseBlock with different data
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-priority",
                    name="StructuredOutput",
                    input={"parameters": {"name": "from-tool-use"}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        # ResultMessage with parameters wrapper in result (should take priority)
        error_result = create_mock_result_message(
            result='{"parameters": {"name": "from-result"}}',
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            # Should use result-based recovery (priority)
            assert parsed == {"name": "from-result"}

    @pytest.mark.asyncio
    async def test_logs_info_on_successful_recovery_from_captured_tool_input(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log INFO when recovery from captured ToolUseBlock succeeds."""
        import logging

        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-log-test",
                    name="StructuredOutput",
                    input={"parameters": {"name": "log-test"}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        error_result = create_mock_result_message(
            result="",
            subtype="error_max_structured_output_retries",
            structured_output=None,
            session_id="captured-recovery-session",
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with caplog.at_level(logging.INFO, logger="claudecode_model.model"):
            with patch("claudecode_model.model.query", mock_query):
                await model.request(messages, None, params)

        # Find the recovery log message
        recovery_logs = [
            r
            for r in caplog.records
            if "recovered" in r.message.lower() and "captured" in r.message.lower()
        ]
        assert len(recovery_logs) == 1
        assert "captured-recovery-session" in recovery_logs[0].message


class TestErrorMaxTurnsStructuredOutputRecovery:
    """Tests for recovery from error_max_turns with structured output.

    When the SDK returns error_max_turns with json_schema enabled, the same
    2-stage recovery logic (parameters wrapper unwrap → captured ToolUseBlock)
    should be applied, identical to error_max_structured_output_retries.
    """

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_turns_with_parameters_wrapper(
        self,
    ) -> None:
        """Should recover from error_max_turns by unwrapping parameters wrapper."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
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

        # SDK returns error_max_turns but with valid parameters wrapper in result
        error_result = create_mock_result_message(
            result='{"parameters": {"name": "test"}}',
            subtype="error_max_turns",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            # Should NOT raise - should recover via parameters unwrap
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "test"}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_turns_with_output_wrapper(
        self,
    ) -> None:
        """Should recover from error_max_turns by unwrapping output wrapper."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "is_complete": {"type": "boolean"},
            },
            "required": ["is_complete"],
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

        # SDK returns error_max_turns with "output" wrapper
        error_result = create_mock_result_message(
            result='{"output": {"is_complete": true}}',
            subtype="error_max_turns",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"is_complete": True}

    @pytest.mark.asyncio
    async def test_recovers_from_error_max_turns_with_json_schema_and_captured_input(
        self,
    ) -> None:
        """Should recover from error_max_turns using captured ToolUseBlock input."""
        from claude_agent_sdk.types import AssistantMessage, ToolUseBlock

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
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

        # AssistantMessage with StructuredOutput ToolUseBlock
        assistant_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tool-max-turns",
                    name="StructuredOutput",
                    input={"parameters": {"name": "captured-test"}},
                )
            ],
            model="claude-sonnet-4-20250514",
        )

        # ResultMessage with empty result (error_max_turns)
        error_result = create_mock_result_message(
            result="",
            subtype="error_max_turns",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield assistant_msg  # type: ignore[misc]
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            parsed = json.loads(content)  # type: ignore[arg-type]
            assert parsed == {"name": "captured-test"}

    @pytest.mark.asyncio
    async def test_raises_error_when_error_max_turns_with_json_schema_no_recovery(
        self,
    ) -> None:
        """Should raise StructuredOutputError when error_max_turns has no recovery path."""
        from claudecode_model.exceptions import StructuredOutputError

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

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

        # Empty result, no captured ToolUseBlock
        error_result = create_mock_result_message(
            result="",
            subtype="error_max_turns",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            with pytest.raises(StructuredOutputError) as exc_info:
                await model.request(messages, None, params)

            assert "recovery failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_error_max_turns_without_json_schema_passes_through(
        self,
    ) -> None:
        """Should pass through error_max_turns without recovery when no json_schema."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]

        # No json_schema (text mode)
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        # error_max_turns with some text result (no json_schema)
        error_result = create_mock_result_message(
            result="some text",
            subtype="error_max_turns",
            structured_output=None,
        )

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            yield error_result

        with patch("claudecode_model.model.query", mock_query):
            # Should NOT raise - passes through as normal response
            response = await model.request(messages, None, params)

            content = response.parts[0].content  # type: ignore[union-attr]
            assert content == "some text"
