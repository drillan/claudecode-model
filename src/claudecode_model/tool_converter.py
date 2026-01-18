"""Convert pydantic-ai Tools to Claude Agent SDK MCP format.

Note:
    This module uses pydantic-ai internal APIs (agent._function_toolset)
    that may change in future versions.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypedDict

from claude_agent_sdk import SdkMcpTool
from pydantic_ai.tools import Tool

if TYPE_CHECKING:
    from typing import Any


class McpServerConfig(TypedDict):
    """Configuration for an MCP server with converted tools."""

    name: str
    version: str
    tools: list[SdkMcpTool[dict[str, Any]]]


def _format_return_value_as_mcp(result: object) -> dict[str, Any]:
    """Convert a return value to MCP format.

    Args:
        result: The return value from a tool function.

    Returns:
        A dict in MCP format with "content" key containing text blocks.

    Examples:
        >>> _format_return_value_as_mcp("hello")
        {'content': [{'type': 'text', 'text': 'hello'}]}
        >>> _format_return_value_as_mcp({"key": "value"})
        {'content': [{'type': 'text', 'text': '{"key": "value"}'}]}
    """
    # Check if already in MCP format
    if isinstance(result, dict) and "content" in result:
        content = result.get("content")
        if isinstance(content, list) and len(content) > 0:
            first_item = content[0]
            if isinstance(first_item, dict) and first_item.get("type") == "text":
                return result  # type: ignore[return-value]

    # Convert to text
    if result is None:
        text = ""
    elif isinstance(result, str):
        text = result
    elif isinstance(result, (dict, list)):
        text = json.dumps(result)
    else:
        text = str(result)

    return {"content": [{"type": "text", "text": text}]}


def _create_async_handler(
    func: Callable[..., Any],
    takes_ctx: bool = False,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Wrap a sync/async function as an async SDK handler.

    Args:
        func: The original tool function (sync or async).
        takes_ctx: Whether the function takes a RunContext as first argument.
                   Currently only False is supported.

    Returns:
        An async function that accepts a dict and returns MCP format response.
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(**args)
            else:
                result = func(**args)
            return _format_return_value_as_mcp(result)
        except Exception as e:
            error_msg = f"Error: {type(e).__name__}: {e}"
            return {"content": [{"type": "text", "text": error_msg}]}

    return handler


def convert_tool(tool: Tool[Any]) -> SdkMcpTool[dict[str, Any]]:
    """Convert a pydantic-ai Tool to SdkMcpTool.

    Args:
        tool: A pydantic-ai Tool object from agent._function_toolset.tools.

    Returns:
        An SdkMcpTool that can be used with Claude Agent SDK.

    Raises:
        TypeError: If the input is not a Tool instance.

    Note:
        This function uses pydantic-ai internal APIs that may change.

    Example:
        >>> from pydantic_ai import Agent
        >>> agent = Agent("test")
        >>> @agent.tool_plain
        ... def get_weather(city: str) -> str:
        ...     return f"Weather in {city}"
        >>> tools = list(agent._function_toolset.tools.values())
        >>> sdk_tool = convert_tool(tools[0])
        >>> sdk_tool.name
        'get_weather'
    """
    if not isinstance(tool, Tool):
        raise TypeError(f"expected Tool, got {type(tool).__name__}")

    tool_def = tool.tool_def
    name = tool_def.name
    description = tool_def.description or ""
    input_schema = tool_def.parameters_json_schema

    handler = _create_async_handler(tool.function, takes_ctx=tool.takes_ctx)

    return SdkMcpTool(
        name=name,
        description=description,
        input_schema=input_schema,
        handler=handler,
    )


def convert_tools_to_mcp_server(
    tools: list[Tool[Any]],
    *,
    server_name: str = "pydantic-tools",
    server_version: str = "1.0.0",
) -> McpServerConfig:
    """Convert a list of pydantic-ai Tools to MCP server configuration.

    Args:
        tools: List of pydantic-ai Tool objects.
        server_name: Name for the MCP server.
        server_version: Version for the MCP server.

    Returns:
        McpServerConfig containing name, version, and converted tools.

    Note:
        This function uses pydantic-ai internal APIs that may change.

    Example:
        >>> from pydantic_ai import Agent
        >>> agent = Agent("test")
        >>> @agent.tool_plain
        ... def get_weather(city: str) -> str:
        ...     return f"Weather in {city}"
        >>> tools = list(agent._function_toolset.tools.values())
        >>> config = convert_tools_to_mcp_server(tools)
        >>> config["name"]
        'pydantic-tools'
    """
    sdk_tools = [convert_tool(tool) for tool in tools]

    return McpServerConfig(
        name=server_name,
        version=server_version,
        tools=sdk_tools,
    )
