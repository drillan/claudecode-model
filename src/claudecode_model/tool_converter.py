"""Convert pydantic-ai Tools to Claude Agent SDK MCP format.

Note:
    This module uses pydantic-ai internal APIs (agent._function_toolset)
    that may change in future versions.

Warning:
    Serializable dependency support (convert_tool_with_deps) is experimental.
    The API may change in future versions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Literal, TypedDict, TypeVar

from claude_agent_sdk import SdkMcpTool
from pydantic_ai.tools import Tool

from claudecode_model.deps_support import DepsContext, create_deps_context

T = TypeVar("T")

logger = logging.getLogger(__name__)


# Type alias for JSON schema dict
type JsonSchema = dict[str, object]


class McpTextContent(TypedDict):
    """MCP text content block."""

    type: Literal["text"]
    text: str


class McpResponse(TypedDict, total=False):
    """MCP response format with content blocks."""

    content: list[McpTextContent]
    isError: bool


class McpServerConfig(TypedDict):
    """Configuration for an MCP server with converted tools."""

    name: str
    version: str
    tools: list[SdkMcpTool[JsonSchema]]


def _format_return_value_as_mcp(result: object) -> McpResponse:
    """Convert a return value to MCP format.

    Args:
        result: The return value from a tool function.

    Returns:
        An McpResponse with "content" key containing text blocks.

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
                # Already in MCP format, cast to McpResponse
                return McpResponse(
                    content=[
                        McpTextContent(type="text", text=item.get("text", ""))
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                )

    # Convert to text
    if result is None:
        text = ""
    elif isinstance(result, str):
        text = result
    elif isinstance(result, (dict, list)):
        text = json.dumps(result)
    else:
        text = str(result)

    return McpResponse(content=[McpTextContent(type="text", text=text)])


def _create_async_handler(
    func: Callable[..., object],
    takes_ctx: bool,
    deps_context: DepsContext[object] | None = None,
) -> Callable[[JsonSchema], Awaitable[dict[str, object]]]:
    """Wrap a sync/async function as an async SDK handler.

    Args:
        func: The original tool function (sync or async).
        takes_ctx: Whether the function takes a RunContext as first argument.
        deps_context: Optional DepsContext for tools that use dependencies.

    Returns:
        An async function that accepts a dict and returns MCP format response.

    Raises:
        NotImplementedError: If takes_ctx is True and no deps_context provided.
    """
    if takes_ctx and deps_context is None:
        raise NotImplementedError(
            "Tools with takes_ctx=True are not supported. "
            "Please use tool_plain decorator instead."
        )

    async def handler(args: JsonSchema) -> dict[str, object]:
        try:
            if takes_ctx and deps_context is not None:
                # Inject the deps context as the first argument
                if asyncio.iscoroutinefunction(func):
                    result = await func(deps_context, **args)
                else:
                    result = func(deps_context, **args)
            else:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**args)
                else:
                    result = func(**args)
            return dict(_format_return_value_as_mcp(result))
        except asyncio.CancelledError:
            raise  # Re-raise to allow proper task cancellation
        except Exception as e:
            logger.exception("Unexpected error during tool execution")
            error_msg = f"Error: {type(e).__name__}: {e}"
            return dict(
                McpResponse(
                    content=[McpTextContent(type="text", text=error_msg)],
                    isError=True,
                )
            )

    return handler


def convert_tool(tool: Tool[object]) -> SdkMcpTool[JsonSchema]:
    """Convert a pydantic-ai Tool to SdkMcpTool.

    Args:
        tool: A pydantic-ai Tool object from agent._function_toolset.tools.

    Returns:
        An SdkMcpTool that can be used with Claude Agent SDK.

    Raises:
        TypeError: If the input is not a Tool instance.
        NotImplementedError: If the tool uses takes_ctx=True.

    Note:
        This function uses pydantic-ai internal APIs that may change.

    Examples:
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


def convert_tool_with_deps(tool: Tool[T], deps: T) -> SdkMcpTool[JsonSchema]:
    """Convert a pydantic-ai Tool with dependencies to SdkMcpTool (experimental).

    This function enables tools that use RunContext to access serializable
    dependencies. The dependencies are provided at conversion time and injected
    into the tool handler when invoked.

    Warning:
        This is an experimental feature. The API may change in future versions.

    Args:
        tool: A pydantic-ai Tool object that uses RunContext with deps.
        deps: The dependency object to inject (must be serializable).

    Returns:
        An SdkMcpTool that can be used with Claude Agent SDK.

    Raises:
        TypeError: If the input is not a Tool instance.
        UnsupportedDepsTypeError: If deps type is not serializable.

    Supported dependency types:
        - dict, list, str, int, float, bool, None
        - dataclass instances
        - Pydantic BaseModel instances

    Note:
        The tool's input schema will not include the 'ctx' parameter,
        as the context is injected automatically at runtime.

    Examples:
        >>> from pydantic_ai import Agent, RunContext
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Config:
        ...     api_key: str
        >>> agent: Agent[Config] = Agent("test")
        >>> @agent.tool
        ... def call_api(ctx: RunContext[Config], endpoint: str) -> str:
        ...     return f"Called {endpoint} with key {ctx.deps.api_key}"
        >>> tools = list(agent._function_toolset.tools.values())
        >>> config = Config(api_key="secret")
        >>> sdk_tool = convert_tool_with_deps(tools[0], config)
    """
    if not isinstance(tool, Tool):
        raise TypeError(f"expected Tool, got {type(tool).__name__}")

    tool_def = tool.tool_def
    name = tool_def.name
    description = tool_def.description or ""
    input_schema = tool_def.parameters_json_schema

    # Create deps context with validation (raises UnsupportedDepsTypeError if not serializable)
    # DepsContext[T] is invariant, but we only read deps via the .deps property,
    # so widening to DepsContext[object] is safe at runtime. The type: ignore
    # suppresses the assignment error from T -> object covariance mismatch.
    deps_context: DepsContext[object] = create_deps_context(deps)  # type: ignore[assignment]

    handler = _create_async_handler(
        tool.function, takes_ctx=tool.takes_ctx, deps_context=deps_context
    )

    return SdkMcpTool(
        name=name,
        description=description,
        input_schema=input_schema,
        handler=handler,
    )


def convert_tools_to_mcp_server(
    tools: list[Tool[object]],
    *,
    server_name: str,
    server_version: str,
) -> McpServerConfig:
    """Convert a list of pydantic-ai Tools to MCP server configuration.

    Args:
        tools: List of pydantic-ai Tool objects.
        server_name: Name for the MCP server (required).
        server_version: Version for the MCP server (required).

    Returns:
        McpServerConfig containing name, version, and converted tools.

    Note:
        This function uses pydantic-ai internal APIs that may change.

    Examples:
        >>> from pydantic_ai import Agent
        >>> agent = Agent("test")
        >>> @agent.tool_plain
        ... def get_weather(city: str) -> str:
        ...     return f"Weather in {city}"
        >>> tools = list(agent._function_toolset.tools.values())
        >>> config = convert_tools_to_mcp_server(
        ...     tools, server_name="my-server", server_version="1.0.0"
        ... )
        >>> config["name"]
        'my-server'
    """
    sdk_tools = [convert_tool(tool) for tool in tools]

    return McpServerConfig(
        name=server_name,
        version=server_version,
        tools=sdk_tools,
    )
