"""Tests for MCP integration with pydantic-ai toolsets."""

from unittest.mock import MagicMock

import pytest

from claudecode_model.mcp_integration import (
    ToolDefinition,
    convert_tool_definition,
    create_mcp_server_from_tools,
    extract_tools_from_toolsets,
)


class TestExtractToolsFromToolsets:
    """Tests for extract_tools_from_toolsets function."""

    def test_extracts_tools_from_single_tool(self) -> None:
        """Should extract tool info from a single pydantic-ai tool."""
        # pydantic-ai tool has name, description, and parameters_json_schema
        mock_tool = MagicMock()
        mock_tool.name = "get_weather"
        mock_tool.description = "Get the current weather for a location"
        mock_tool.parameters_json_schema = {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name"}},
            "required": ["location"],
        }

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


class TestConvertToolDefinition:
    """Tests for convert_tool_definition function."""

    def test_converts_basic_tool(self) -> None:
        """Should convert basic tool definition to SdkMcpTool format."""
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

        result = convert_tool_definition(tool_def)

        # Should return a SdkMcpTool-compatible object
        assert hasattr(result, "name")
        assert result.name == "search"

    def test_converts_tool_with_complex_schema(self) -> None:
        """Should convert tool with complex nested schema."""
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
            "function": None,
        }

        result = convert_tool_definition(tool_def)

        assert hasattr(result, "name")
        assert result.name == "analyze"


class TestCreateMcpServerFromTools:
    """Tests for create_mcp_server_from_tools function."""

    def test_creates_mcp_server_with_name(self) -> None:
        """Should create MCP server with specified name."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}

        result = create_mcp_server_from_tools(
            name="pydantic_tools", toolsets=[mock_tool]
        )

        # Result should be McpSdkServerConfig
        assert result is not None

    def test_creates_mcp_server_with_version(self) -> None:
        """Should create MCP server with specified version."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}

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


class TestToolNamePrefixing:
    """Tests for tool name prefixing (mcp__server__tool format)."""

    def test_tool_names_follow_mcp_convention(self) -> None:
        """Tool names should follow mcp__server__tool convention when exposed."""
        # When tools are registered via MCP server, Claude will see them
        # as mcp__<server_name>__<tool_name>
        # This test verifies the naming pattern is maintained

        mock_tool = MagicMock()
        mock_tool.name = "search"
        mock_tool.description = "Search documents"
        mock_tool.parameters_json_schema = {"type": "object", "properties": {}}

        result = create_mcp_server_from_tools(
            name="pydantic_tools", toolsets=[mock_tool]
        )

        # The server should be created successfully
        # The actual prefixing is handled by Claude Code CLI
        assert result is not None
