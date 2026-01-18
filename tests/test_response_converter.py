"""Tests for response_converter module - SDK to CLIResponse conversion."""

from __future__ import annotations

import pytest
from claude_agent_sdk.types import (
    AssistantMessage,
    Message,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from claudecode_model.response_converter import (
    convert_sdk_messages_to_cli_response,
    convert_usage_dict_to_cli_usage,
    extract_text_from_assistant_message,
)
from claudecode_model.types import CLIUsage, JsonValue


class TestExtractTextFromAssistantMessage:
    """Tests for extract_text_from_assistant_message function."""

    def test_extracts_single_text_block(self) -> None:
        """Single TextBlock should extract its text content."""
        message = AssistantMessage(
            content=[TextBlock(text="Hello, world!")],
            model="claude-3-opus-20240229",
        )
        result = extract_text_from_assistant_message(message)
        assert result == "Hello, world!"

    def test_extracts_multiple_text_blocks(self) -> None:
        """Multiple TextBlocks should be joined with newline."""
        message = AssistantMessage(
            content=[
                TextBlock(text="First paragraph."),
                TextBlock(text="Second paragraph."),
                TextBlock(text="Third paragraph."),
            ],
            model="claude-3-opus-20240229",
        )
        result = extract_text_from_assistant_message(message)
        assert result == "First paragraph.\nSecond paragraph.\nThird paragraph."

    def test_ignores_thinking_blocks(self) -> None:
        """ThinkingBlock should be ignored during extraction."""
        message = AssistantMessage(
            content=[
                ThinkingBlock(thinking="Internal reasoning...", signature="abc"),
                TextBlock(text="Visible response"),
            ],
            model="claude-3-opus-20240229",
        )
        result = extract_text_from_assistant_message(message)
        assert result == "Visible response"
        assert "Internal reasoning" not in result

    def test_ignores_tool_use_blocks(self) -> None:
        """ToolUseBlock should be ignored during extraction."""
        message = AssistantMessage(
            content=[
                TextBlock(text="Let me help you."),
                ToolUseBlock(id="tool_1", name="read_file", input={"path": "/tmp/x"}),
                TextBlock(text="Done."),
            ],
            model="claude-3-opus-20240229",
        )
        result = extract_text_from_assistant_message(message)
        assert result == "Let me help you.\nDone."

    def test_returns_empty_string_for_no_text_blocks(self) -> None:
        """No TextBlocks should return empty string."""
        message = AssistantMessage(
            content=[
                ThinkingBlock(thinking="Thinking...", signature="sig"),
                ToolUseBlock(id="tool_1", name="bash", input={"cmd": "ls"}),
            ],
            model="claude-3-opus-20240229",
        )
        result = extract_text_from_assistant_message(message)
        assert result == ""


class TestConvertUsageDictToCLIUsage:
    """Tests for convert_usage_dict_to_cli_usage function."""

    def test_converts_complete_usage_dict(self) -> None:
        """Complete usage dict should be fully converted."""
        usage_dict: dict[str, JsonValue] = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 200,
            "service_tier": "standard",
            "server_tool_use": {
                "web_search_requests": 2,
                "web_fetch_requests": 3,
            },
            "cache_creation": {
                "ephemeral_1h_input_tokens": 50,
                "ephemeral_5m_input_tokens": 25,
            },
        }
        result = convert_usage_dict_to_cli_usage(usage_dict)

        assert isinstance(result, CLIUsage)
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cache_creation_input_tokens == 100
        assert result.cache_read_input_tokens == 200
        assert result.service_tier == "standard"
        assert result.server_tool_use is not None
        assert result.server_tool_use.web_search_requests == 2
        assert result.server_tool_use.web_fetch_requests == 3
        assert result.cache_creation is not None
        assert result.cache_creation.ephemeral_1h_input_tokens == 50
        assert result.cache_creation.ephemeral_5m_input_tokens == 25

    def test_converts_minimal_usage_dict(self) -> None:
        """Minimal usage dict with only required fields."""
        usage_dict: dict[str, JsonValue] = {
            "input_tokens": 100,
            "output_tokens": 50,
        }
        result = convert_usage_dict_to_cli_usage(usage_dict)

        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_creation_input_tokens == 0
        assert result.cache_read_input_tokens == 0
        assert result.server_tool_use is None
        assert result.cache_creation is None

    def test_converts_none_to_default_usage(self) -> None:
        """None should return default CLIUsage with all zeros."""
        result = convert_usage_dict_to_cli_usage(None)

        assert isinstance(result, CLIUsage)
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cache_creation_input_tokens == 0
        assert result.cache_read_input_tokens == 0
        assert result.server_tool_use is None
        assert result.service_tier is None
        assert result.cache_creation is None

    def test_handles_missing_optional_fields(self) -> None:
        """Missing optional fields should use defaults."""
        usage_dict: dict[str, JsonValue] = {
            "input_tokens": 500,
            "output_tokens": 250,
            "cache_read_input_tokens": 100,
            # Missing: cache_creation_input_tokens, service_tier, server_tool_use, cache_creation
        }
        result = convert_usage_dict_to_cli_usage(usage_dict)

        assert result.input_tokens == 500
        assert result.output_tokens == 250
        assert result.cache_read_input_tokens == 100
        assert result.cache_creation_input_tokens == 0
        assert result.server_tool_use is None
        assert result.service_tier is None
        assert result.cache_creation is None


class TestConvertSdkMessagesToCLIResponse:
    """Tests for convert_sdk_messages_to_cli_response function."""

    def _create_result_message(
        self,
        *,
        result: str | None = "Test result",
        structured_output: object = None,
        subtype: str = "success",
        is_error: bool = False,
        duration_ms: int = 1000,
        duration_api_ms: int = 800,
        num_turns: int = 1,
        session_id: str = "session-123",
        total_cost_usd: float | None = 0.05,
        usage: dict[str, object] | None = None,
    ) -> ResultMessage:
        """Helper to create ResultMessage with defaults."""
        return ResultMessage(
            result=result,
            structured_output=structured_output,
            subtype=subtype,
            is_error=is_error,
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            num_turns=num_turns,
            session_id=session_id,
            total_cost_usd=total_cost_usd,
            usage=usage,
        )

    def test_converts_basic_messages(self) -> None:
        """Basic messages list should convert to CLIResponse."""
        result_msg = self._create_result_message()
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.result == "Test result"
        assert response.subtype == "success"
        assert response.is_error is False
        assert response.duration_ms == 1000
        assert response.duration_api_ms == 800
        assert response.num_turns == 1
        assert response.session_id == "session-123"
        assert response.total_cost_usd == 0.05

    def test_extracts_text_from_assistant_messages(self) -> None:
        """AssistantMessage text should be extracted when no ResultMessage result."""
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Assistant response text")],
            model="claude-3-opus-20240229",
        )
        result_msg = self._create_result_message(result=None)
        messages: list[Message] = [assistant_msg, result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.result == "Assistant response text"

    def test_requires_result_message(self) -> None:
        """Missing ResultMessage should raise ValueError."""
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-3-opus-20240229",
        )
        messages = [assistant_msg]

        with pytest.raises(ValueError, match="ResultMessage.*required"):
            convert_sdk_messages_to_cli_response(messages)

    def test_uses_result_message_result_field(self) -> None:
        """ResultMessage.result should take priority over extracted text."""
        assistant_msg = AssistantMessage(
            content=[TextBlock(text="This should be ignored")],
            model="claude-3-opus-20240229",
        )
        result_msg = self._create_result_message(result="Priority result")
        messages: list[Message] = [assistant_msg, result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.result == "Priority result"
        assert "ignored" not in response.result

    def test_sets_default_type_to_result(self) -> None:
        """Default type should be 'result'."""
        result_msg = self._create_result_message()
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.type == "result"

    def test_handles_empty_message_list(self) -> None:
        """Empty messages list should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            convert_sdk_messages_to_cli_response([])

    def test_handles_structured_output(self) -> None:
        """structured_output dict should be preserved."""
        structured = {"key": "value", "nested": {"a": 1}}
        result_msg = self._create_result_message(
            result=None,
            structured_output=structured,
        )
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.structured_output == structured
        assert response.result == ""

    def test_handles_error_state(self) -> None:
        """is_error=True should be reflected in response."""
        result_msg = self._create_result_message(
            result="Error occurred",
            is_error=True,
            subtype="error",
        )
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.is_error is True
        assert response.subtype == "error"
        assert response.result == "Error occurred"

    def test_sets_unavailable_fields_to_none(self) -> None:
        """Fields not available in SDK should be None."""
        result_msg = self._create_result_message()
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.model_usage is None
        assert response.permission_denials is None
        assert response.uuid is None
        assert response.errors is None

    def test_handles_usage_conversion(self) -> None:
        """usage dict should be converted to CLIUsage."""
        usage_data: dict[str, object] = {
            "input_tokens": 500,
            "output_tokens": 200,
            "cache_read_input_tokens": 100,
        }
        result_msg = self._create_result_message(usage=usage_data)
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.usage.input_tokens == 500
        assert response.usage.output_tokens == 200
        assert response.usage.cache_read_input_tokens == 100

    def test_custom_default_type(self) -> None:
        """Custom default_type should be used."""
        result_msg = self._create_result_message()
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(
            messages, default_type="custom_type"
        )

        assert response.type == "custom_type"

    def test_uses_last_result_message(self) -> None:
        """When multiple ResultMessages exist, use the last one."""
        result_msg1 = self._create_result_message(result="First result")
        result_msg2 = self._create_result_message(result="Last result")
        messages = [result_msg1, result_msg2]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.result == "Last result"

    def test_combines_text_from_multiple_assistant_messages(self) -> None:
        """Multiple AssistantMessages should have their text combined."""
        assistant_msg1 = AssistantMessage(
            content=[TextBlock(text="First message")],
            model="claude-3-opus-20240229",
        )
        assistant_msg2 = AssistantMessage(
            content=[TextBlock(text="Second message")],
            model="claude-3-opus-20240229",
        )
        result_msg = self._create_result_message(result=None)
        messages: list[Message] = [assistant_msg1, assistant_msg2, result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert "First message" in response.result
        assert "Second message" in response.result

    def test_non_dict_structured_output_ignored(self) -> None:
        """Non-dict structured_output should be None in response."""
        result_msg = self._create_result_message(
            result="Has result",
            structured_output="not a dict",
        )
        messages = [result_msg]

        response = convert_sdk_messages_to_cli_response(messages)

        assert response.structured_output is None
        assert response.result == "Has result"
