"""Tests for ClaudeCodeModel agent options and toolsets functionality."""

import logging
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.cli import DEFAULT_MODEL
from claudecode_model.model import ClaudeCodeModel
from claudecode_model.types import JsonValue


class TestClaudeCodeModelBuildAgentOptions:
    """Tests for ClaudeCodeModel._build_agent_options method."""

    def test_build_agent_options_default_values(self) -> None:
        """_build_agent_options should use default model values."""
        model = ClaudeCodeModel()
        options = model._build_agent_options()

        assert isinstance(options, ClaudeAgentOptions)
        assert options.model == DEFAULT_MODEL
        assert options.cwd is None
        assert options.allowed_tools is None
        assert options.disallowed_tools == []
        assert options.permission_mode is None
        assert options.max_turns is None
        assert options.max_budget_usd is None
        assert options.system_prompt is None
        assert options.output_format is None

    def test_build_agent_options_with_custom_model_values(self) -> None:
        """_build_agent_options should use custom model values from __init__."""
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

    def test_build_agent_options_with_empty_allowed_tools(self) -> None:
        """_build_agent_options should preserve empty list for allowed_tools."""
        model = ClaudeCodeModel(allowed_tools=[])
        options = model._build_agent_options()

        assert options.allowed_tools == []
        assert options.allowed_tools is not None

    def test_build_agent_options_with_override_values(self) -> None:
        """_build_agent_options should allow override values via parameters."""
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
        model = ClaudeCodeModel()
        options = model._build_agent_options(json_schema=None)

        assert isinstance(options, ClaudeAgentOptions)
        assert options.output_format is None

    def test_build_agent_options_with_append_system_prompt(self) -> None:
        """_build_agent_options should combine system_prompt and append_system_prompt."""
        model = ClaudeCodeModel()
        options = model._build_agent_options(
            system_prompt="Main prompt",
            append_system_prompt="Additional instructions",
        )

        assert isinstance(options, ClaudeAgentOptions)
        assert options.system_prompt == "Main prompt\n\nAdditional instructions"

    def test_build_agent_options_with_only_append_system_prompt(self) -> None:
        """_build_agent_options should use append_system_prompt alone when system_prompt is None."""
        model = ClaudeCodeModel()
        options = model._build_agent_options(
            system_prompt=None,
            append_system_prompt="Additional instructions",
        )

        assert isinstance(options, ClaudeAgentOptions)
        assert options.system_prompt == "Additional instructions"


class TestClaudeCodeModelSetAgentToolsets:
    """Tests for ClaudeCodeModel.set_agent_toolsets method."""

    def test_set_agent_toolsets_registers_toolsets(self) -> None:
        """set_agent_toolsets should register toolsets internally."""

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
        assert isinstance(model._agent_toolsets, list)
        assert len(model._agent_toolsets) == 1

    def test_set_agent_toolsets_creates_mcp_server(self) -> None:
        """set_agent_toolsets should create MCP server from toolsets."""

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
        assert isinstance(model._agent_toolsets, list)
        assert len(model._agent_toolsets) == 2

    def test_get_mcp_servers_returns_registered_servers(self) -> None:
        """get_mcp_servers should return registered MCP servers."""

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
        model = ClaudeCodeModel()

        # First call - no warning
        model.set_agent_toolsets([])

        # Second call - should log warning
        with caplog.at_level(logging.WARNING):
            model.set_agent_toolsets(None)

        assert "Overwriting" in caplog.text
        assert "pydantic_tools" in caplog.text


class TestBuildAgentOptionsMcpServers:
    """Tests for _build_agent_options passing mcp_servers to ClaudeAgentOptions."""

    def test_build_agent_options_passes_mcp_servers(self) -> None:
        """_build_agent_options should pass mcp_servers to ClaudeAgentOptions."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        # Register toolsets to populate _mcp_servers
        model.set_agent_toolsets([mock_tool])

        # Build agent options
        options = model._build_agent_options()

        # Verify mcp_servers is passed to ClaudeAgentOptions
        assert options.mcp_servers is not None
        assert isinstance(options.mcp_servers, dict)
        assert "pydantic_tools" in options.mcp_servers

    def test_build_agent_options_empty_mcp_servers_when_no_toolsets(self) -> None:
        """_build_agent_options should pass empty mcp_servers when no toolsets registered."""
        model = ClaudeCodeModel()

        # Build agent options without setting toolsets
        options = model._build_agent_options()

        # mcp_servers should be empty dict
        assert options.mcp_servers == {}

    @pytest.mark.asyncio
    async def test_request_passes_mcp_servers_to_sdk(self) -> None:
        """request should pass mcp_servers to SDK via ClaudeAgentOptions."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        model = ClaudeCodeModel()
        mock_tool = MagicMock()
        mock_tool.name = "weather"
        mock_tool.description = "Get weather"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        model.set_agent_toolsets([mock_tool])

        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
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

        assert len(captured_options) == 1
        assert captured_options[0].mcp_servers is not None
        assert isinstance(captured_options[0].mcp_servers, dict)
        assert "pydantic_tools" in captured_options[0].mcp_servers
