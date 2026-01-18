"""MCP integration utilities for pydantic-ai toolsets.

This module provides functions to convert pydantic-ai tools to
Claude Agent SDK MCP server format.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from typing import Protocol, TypedDict, runtime_checkable

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from claudecode_model.types import JsonValue


class ToolDefinition(TypedDict):
    """Tool definition extracted from pydantic-ai toolset."""

    name: str
    description: str
    input_schema: dict[str, JsonValue]
    function: Callable[..., Coroutine[object, object, object]] | None


@runtime_checkable
class PydanticAITool(Protocol):
    """Protocol for pydantic-ai tool interface."""

    name: str
    description: str
    parameters_json_schema: dict[str, JsonValue]


def extract_tools_from_toolsets(
    toolsets: Sequence[PydanticAITool] | None,
) -> list[ToolDefinition]:
    """Extract tool definitions from pydantic-ai toolsets.

    Args:
        toolsets: Sequence of pydantic-ai tool objects or None.

    Returns:
        List of tool definitions with name, description, and input_schema.
    """
    if toolsets is None:
        return []

    result: list[ToolDefinition] = []
    for t in toolsets:
        tool_def: ToolDefinition = {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters_json_schema,
            "function": getattr(t, "function", None),
        }
        result.append(tool_def)
    return result


def convert_tool_definition(tool_def: ToolDefinition) -> SdkMcpTool[dict[str, object]]:
    """Convert a tool definition to SdkMcpTool format.

    Args:
        tool_def: Tool definition with name, description, input_schema, and function.

    Returns:
        SdkMcpTool instance compatible with create_sdk_mcp_server.
    """
    original_function = tool_def.get("function")

    @tool(tool_def["name"], tool_def["description"], tool_def["input_schema"])
    async def wrapper(args: dict[str, object]) -> dict[str, object]:
        """Wrapper that delegates to original pydantic-ai tool function."""
        if original_function is not None:
            # Call the original function with the args
            result = await original_function(**args)
            return {"content": [{"type": "text", "text": str(result)}]}
        return {"content": [{"type": "text", "text": "No function registered"}]}

    return wrapper


def create_mcp_server_from_tools(
    name: str,
    toolsets: Sequence[PydanticAITool] | None,
    version: str = "1.0.0",
) -> McpSdkServerConfig:
    """Create an MCP server from pydantic-ai toolsets.

    Args:
        name: Server name (used as prefix in mcp__<name>__<tool>).
        toolsets: Sequence of pydantic-ai tool objects.
        version: Server version string.

    Returns:
        McpSdkServerConfig for use with ClaudeAgentOptions.mcp_servers.
    """
    tool_defs = extract_tools_from_toolsets(toolsets)
    sdk_tools = [convert_tool_definition(td) for td in tool_defs]

    return create_sdk_mcp_server(
        name=name,
        version=version,
        tools=sdk_tools if sdk_tools else None,
    )
