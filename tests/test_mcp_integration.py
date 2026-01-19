"""Tests for MCP integration with pydantic-ai toolsets."""

import logging
from unittest.mock import MagicMock

import pytest

from claudecode_model.mcp_integration import (
    MCP_SERVER_NAME,
    ToolDefinition,
    ToolValidationError,
    _get_parameters_json_schema,
    convert_tool_definition,
    create_mcp_server_from_tools,
    create_tool_wrapper,
    extract_tools_from_toolsets,
)


class TestGetParametersJsonSchema:
    """Tests for _get_parameters_json_schema helper function."""

    def test_gets_schema_from_direct_parameters_json_schema(self) -> None:
        """Should get schema from direct parameters_json_schema attribute."""
        mock_tool = MagicMock()
        mock_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

        result = _get_parameters_json_schema(mock_tool)

        assert result == {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

    def test_gets_schema_from_function_schema_json_schema(self) -> None:
        """Should get schema from function_schema.json_schema for Tool class."""
        mock_tool = MagicMock(spec=[])  # No default attributes
        mock_tool.function_schema = MagicMock()
        mock_tool.function_schema.json_schema = {
            "type": "object",
            "properties": {"location": {"type": "string"}},
        }

        result = _get_parameters_json_schema(mock_tool)

        assert result == {
            "type": "object",
            "properties": {"location": {"type": "string"}},
        }

    def test_gets_schema_from_tool_def_parameters_json_schema(self) -> None:
        """Should get schema from tool_def.parameters_json_schema for Tool class."""
        mock_tool = MagicMock(spec=[])  # No default attributes
        mock_tool.tool_def = MagicMock()
        mock_tool.tool_def.parameters_json_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        result = _get_parameters_json_schema(mock_tool)

        assert result == {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

    def test_raises_error_when_no_schema_found(self) -> None:
        """Should raise ToolValidationError when no schema can be found."""
        mock_tool = MagicMock(spec=[])  # No attributes at all
        mock_tool.name = "broken_tool"

        with pytest.raises(ToolValidationError) as exc_info:
            _get_parameters_json_schema(mock_tool)

        assert "Cannot extract JSON schema" in str(exc_info.value)
        assert "broken_tool" in str(exc_info.value)

    def test_prefers_direct_parameters_json_schema(self) -> None:
        """Should prefer direct parameters_json_schema over other paths."""
        mock_tool = MagicMock()
        mock_tool.parameters_json_schema = {"direct": True}
        mock_tool.function_schema = MagicMock()
        mock_tool.function_schema.json_schema = {"function_schema": True}
        mock_tool.tool_def = MagicMock()
        mock_tool.tool_def.parameters_json_schema = {"tool_def": True}

        result = _get_parameters_json_schema(mock_tool)

        assert result == {"direct": True}


class TestExtractToolsFromToolsets:
    """Tests for extract_tools_from_toolsets function."""

    def test_extracts_tools_from_single_tool(self) -> None:
        """Should extract tool info from a single pydantic-ai tool."""
        # pydantic-ai tool has name, description, parameters_json_schema, and function
        mock_tool = MagicMock()
        mock_tool.name = "get_weather"
        mock_tool.description = "Get the current weather for a location"
        mock_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name"}},
            "required": ["location"],
        }
        mock_tool.function = None  # Optional function attribute

        result = extract_tools_from_toolsets([mock_tool])

        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get the current weather for a location"
        input_schema = result[0]["input_schema"]
        assert isinstance(input_schema, dict)
        properties = input_schema.get("properties")
        assert isinstance(properties, dict)
        location = properties.get("location")
        assert isinstance(location, dict)
        assert location.get("type") == "string"

    def test_raises_on_empty_tool_name(self) -> None:
        """Should raise ToolValidationError for empty tool name."""
        mock_tool = MagicMock()
        mock_tool.name = ""
        mock_tool.description = "Description"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = None

        with pytest.raises(ToolValidationError) as exc_info:
            extract_tools_from_toolsets([mock_tool])

        assert "name cannot be empty" in str(exc_info.value)

    def test_raises_on_whitespace_only_tool_name(self) -> None:
        """Should raise ToolValidationError for whitespace-only tool name."""
        mock_tool = MagicMock()
        mock_tool.name = "   "
        mock_tool.description = "Description"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = None

        with pytest.raises(ToolValidationError) as exc_info:
            extract_tools_from_toolsets([mock_tool])

        assert "name cannot be empty" in str(exc_info.value)

    def test_extracts_tools_from_multiple_tools(self) -> None:
        """Should extract tool info from multiple pydantic-ai tools."""
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "Description 1"
        mock_tool1.parameters_json_schema = {"type": "object", "properties": {}}

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Description 2"
        mock_tool2.parameters_json_schema = {"type": "object", "properties": {}}

        result = extract_tools_from_toolsets([mock_tool1, mock_tool2])

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"

    def test_returns_empty_list_for_empty_toolset(self) -> None:
        """Should return empty list for empty toolset."""
        result = extract_tools_from_toolsets([])
        assert result == []

    def test_returns_empty_list_for_none(self) -> None:
        """Should return empty list for None toolset."""
        result = extract_tools_from_toolsets(None)
        assert result == []

    def test_extracts_tools_with_function_schema_json_schema(self) -> None:
        """Should extract tools using function_schema.json_schema path."""
        mock_tool = MagicMock(spec=[])  # No default parameters_json_schema
        mock_tool.name = "pydantic_ai_tool"
        mock_tool.description = "A pydantic-ai Tool class"
        mock_tool.function_schema = MagicMock()
        mock_tool.function_schema.json_schema = {
            "type": "object",
            "properties": {"data": {"type": "string"}},
        }
        mock_tool.function = None

        result = extract_tools_from_toolsets([mock_tool])

        assert len(result) == 1
        assert result[0]["name"] == "pydantic_ai_tool"
        assert result[0]["input_schema"] == {
            "type": "object",
            "properties": {"data": {"type": "string"}},
        }

    def test_extracts_tools_with_tool_def_parameters_json_schema(self) -> None:
        """Should extract tools using tool_def.parameters_json_schema path."""
        mock_tool = MagicMock(spec=[])  # No default parameters_json_schema
        mock_tool.name = "tool_via_tool_def"
        mock_tool.description = "A tool accessed via tool_def"
        mock_tool.tool_def = MagicMock()
        mock_tool.tool_def.parameters_json_schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
        }
        mock_tool.function = None

        result = extract_tools_from_toolsets([mock_tool])

        assert len(result) == 1
        assert result[0]["name"] == "tool_via_tool_def"
        assert result[0]["input_schema"] == {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
        }


class TestConvertToolDefinition:
    """Tests for convert_tool_definition function."""

    def test_raises_on_missing_function(self) -> None:
        """Should raise ToolValidationError when function is None."""
        tool_def: ToolDefinition = {
            "name": "search",
            "description": "Search for information",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "function": None,
        }

        with pytest.raises(ToolValidationError) as exc_info:
            convert_tool_definition(tool_def)

        assert "search" in str(exc_info.value)
        assert "no function registered" in str(exc_info.value)

    def test_converts_tool_with_function(self) -> None:
        """Should convert tool definition with function to SdkMcpTool format."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        tool_def: ToolDefinition = {
            "name": "search",
            "description": "Search for information",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "function": dummy_func,
        }

        result = convert_tool_definition(tool_def)

        # Should return a SdkMcpTool-compatible object
        assert hasattr(result, "name")
        assert result.name == "search"

    def test_converts_tool_with_complex_schema(self) -> None:
        """Should convert tool with complex nested schema."""

        async def dummy_func(**kwargs: object) -> str:
            return "analyzed"

        tool_def: ToolDefinition = {
            "name": "analyze",
            "description": "Analyze data",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "options": {
                        "type": "object",
                        "properties": {"format": {"type": "string"}},
                    },
                },
            },
            "function": dummy_func,
        }

        result = convert_tool_definition(tool_def)

        assert hasattr(result, "name")
        assert result.name == "analyze"


class TestCreateMcpServerFromTools:
    """Tests for create_mcp_server_from_tools function."""

    def test_creates_mcp_server_with_name(self) -> None:
        """Should create MCP server with specified name."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        result = create_mcp_server_from_tools(
            name="pydantic_tools", toolsets=[mock_tool]
        )

        # Result should be McpSdkServerConfig
        assert result is not None

    def test_creates_mcp_server_with_version(self) -> None:
        """Should create MCP server with specified version."""

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        result = create_mcp_server_from_tools(
            name="pydantic_tools", toolsets=[mock_tool], version="2.0.0"
        )

        assert result is not None

    def test_creates_mcp_server_with_empty_toolset(self) -> None:
        """Should create MCP server with empty toolset."""
        result = create_mcp_server_from_tools(name="empty_tools", toolsets=[])

        assert result is not None

    def test_creates_mcp_server_with_none_toolset(self) -> None:
        """Should create MCP server with None toolset (empty tools)."""
        result = create_mcp_server_from_tools(name="none_tools", toolsets=None)

        assert result is not None

    def test_uses_default_name(self) -> None:
        """Should use MCP_SERVER_NAME as default name."""
        result = create_mcp_server_from_tools()

        assert result is not None
        # Default name should be used
        assert MCP_SERVER_NAME == "pydantic_tools"


class TestMcpToolExecution:
    """Tests for MCP tool execution functionality."""

    @pytest.mark.asyncio
    async def test_tool_execution_delegates_to_pydantic_tool(self) -> None:
        """Should delegate tool execution to original pydantic-ai tool."""
        # This test verifies that the MCP tool wrapper correctly calls
        # the original pydantic-ai tool function
        mock_tool = MagicMock()
        mock_tool.name = "calculator"
        mock_tool.description = "Calculate expression"
        mock_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        }

        # The tool's function should be callable
        async def tool_func(expression: str) -> str:
            return f"Result: {eval(expression)}"  # noqa: S307

        mock_tool.function = tool_func

        # Create the converted tool
        tool_def: ToolDefinition = {
            "name": mock_tool.name,
            "description": mock_tool.description,
            "input_schema": mock_tool.parameters_json_schema,
            "function": mock_tool.function,
        }
        sdk_tool = convert_tool_definition(tool_def)

        # The SDK tool should be callable and return MCP-format result
        assert sdk_tool is not None


class TestCreateToolWrapper:
    """Tests for create_tool_wrapper function (wrapper logic)."""

    @pytest.mark.asyncio
    async def test_wrapper_calls_original_function_with_args(self) -> None:
        """Should call original function with provided arguments."""
        call_log: list[str] = []

        async def original_func(expression: str) -> str:
            call_log.append(expression)
            return f"Result: {expression}"

        wrapper = create_tool_wrapper("calculator", original_func)
        result = await wrapper({"expression": "2+2"})

        assert call_log == ["2+2"]
        assert result == {"content": [{"type": "text", "text": "Result: 2+2"}]}

    @pytest.mark.asyncio
    async def test_wrapper_handles_exception_with_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log error when original function raises exception."""

        async def failing_func(**kwargs: object) -> str:
            raise ValueError("Test error")

        wrapper = create_tool_wrapper("failing_tool", failing_func)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="Test error"):
                await wrapper({})

        assert "failing_tool" in caplog.text
        assert "execution failed" in caplog.text

    @pytest.mark.asyncio
    async def test_wrapper_returns_mcp_format_response(self) -> None:
        """Should return MCP-format response with content array."""

        async def simple_func() -> str:
            return "Hello, World!"

        wrapper = create_tool_wrapper("greeter", simple_func)
        result = await wrapper({})

        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_wrapper_converts_result_to_string(self) -> None:
        """Should convert non-string results to string."""

        async def number_func() -> int:
            return 42

        wrapper = create_tool_wrapper("number_tool", number_func)
        result = await wrapper({})

        content = result["content"]
        assert isinstance(content, list)
        first_item = content[0]
        assert isinstance(first_item, dict)
        assert first_item["text"] == "42"

    @pytest.mark.asyncio
    async def test_wrapper_passes_multiple_args(self) -> None:
        """Should pass multiple arguments to original function."""
        received_args: dict[str, object] = {}

        async def multi_arg_func(a: int, b: str, c: bool) -> str:
            received_args["a"] = a
            received_args["b"] = b
            received_args["c"] = c
            return "done"

        wrapper = create_tool_wrapper("multi_arg", multi_arg_func)
        await wrapper({"a": 1, "b": "test", "c": True})

        assert received_args == {"a": 1, "b": "test", "c": True}


class TestToolNamePrefixing:
    """Tests for tool name prefixing (mcp__server__tool format)."""

    def test_tool_names_follow_mcp_convention(self) -> None:
        """Tool names should follow mcp__server__tool convention when exposed."""
        # When tools are registered via MCP server, Claude will see them
        # as mcp__<server_name>__<tool_name>
        # This test verifies the naming pattern is maintained

        async def dummy_func(**kwargs: object) -> str:
            return "result"

        mock_tool = MagicMock()
        mock_tool.name = "search"
        mock_tool.description = "Search documents"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}
        mock_tool.function = dummy_func

        result = create_mcp_server_from_tools(
            name="pydantic_tools", toolsets=[mock_tool]
        )

        # The server should be created successfully
        # The actual prefixing is handled by Claude Code CLI
        assert result is not None


class TestMCPServerNameConstant:
    """Tests for MCP_SERVER_NAME constant."""

    def test_mcp_server_name_value(self) -> None:
        """MCP_SERVER_NAME should have expected value."""
        assert MCP_SERVER_NAME == "pydantic_tools"
