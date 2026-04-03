"""Convert pydantic-ai Tools to Claude Agent SDK MCP format.

Note:
    Use ``agent.toolsets[0]`` (public API) to access the agent's
    ``FunctionToolset``, then ``.tools`` to get individual ``Tool`` objects.

Warning:
    Serializable dependency support (convert_tool_with_deps) is experimental.
    The API may change in future versions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Literal, TypedDict

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic_ai.tools import Tool

from claudecode_model.deps_support import (
    DepsContext,
    ToolCallContext,
    create_deps_context,
)

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
    elif isinstance(result, dict | list):
        text = json.dumps(result)
    else:
        text = str(result)

    return McpResponse(content=[McpTextContent(type="text", text=text)])


def create_async_handler(
    func: Callable[..., object],
    takes_ctx: bool,
    deps_context: ToolCallContext[object] | DepsContext[object] | None = None,
) -> Callable[[JsonSchema], Awaitable[dict[str, object]]]:
    """Wrap a sync/async function as an async SDK handler.

    Args:
        func: The original tool function (sync or async).
        takes_ctx: Whether the function takes a RunContext as first argument.
        deps_context: Optional context for tools that use dependencies.
            Accepts both ToolCallContext (no serialization check) and
            DepsContext (with serialization check).

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
        tool: A pydantic-ai Tool object from agent's FunctionToolset.

    Returns:
        An SdkMcpTool that can be used with Claude Agent SDK.

    Raises:
        TypeError: If the input is not a Tool instance.
        NotImplementedError: If the tool uses takes_ctx=True.

    Examples:
        >>> from pydantic_ai import Agent
        >>> from pydantic_ai.toolsets.function import FunctionToolset
        >>> agent = Agent("test")
        >>> @agent.tool_plain
        ... def get_weather(city: str) -> str:
        ...     return f"Weather in {city}"
        >>> toolset = agent.toolsets[0]
        >>> assert isinstance(toolset, FunctionToolset)
        >>> tools = list(toolset.tools.values())
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

    handler = create_async_handler(tool.function, takes_ctx=tool.takes_ctx)

    return SdkMcpTool(
        name=name,
        description=description,
        input_schema=input_schema,
        handler=handler,
    )


def convert_tool_with_deps[T](tool: Tool[T], deps: T) -> SdkMcpTool[JsonSchema]:
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
        >>> from pydantic_ai.toolsets.function import FunctionToolset
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Config:
        ...     api_key: str
        >>> agent: Agent[Config] = Agent("test")
        >>> @agent.tool
        ... def call_api(ctx: RunContext[Config], endpoint: str) -> str:
        ...     return f"Called {endpoint} with key {ctx.deps.api_key}"
        >>> toolset = agent.toolsets[0]
        >>> assert isinstance(toolset, FunctionToolset)
        >>> tools = list(toolset.tools.values())
        >>> config = Config(api_key="secret")
        >>> sdk_tool = convert_tool_with_deps(tools[0], config)
    """
    if not isinstance(tool, Tool):
        raise TypeError(f"expected Tool, got {type(tool).__name__}")

    # Create deps context with validation (raises UnsupportedDepsTypeError if not serializable)
    # DepsContext[T] is invariant, but we only read deps via the .deps property,
    # so widening to DepsContext[object] is safe at runtime. The type: ignore
    # suppresses the assignment error from T -> object covariance mismatch.
    deps_context: DepsContext[object] = create_deps_context(deps)  # type: ignore[assignment]

    return convert_tool_with_context(tool, deps_context)  # type: ignore[arg-type]


def convert_tool_with_context(
    tool: Tool[object],
    deps_context: ToolCallContext[object] | DepsContext[object],
) -> SdkMcpTool[JsonSchema]:
    """Convert a pydantic-ai Tool using a pre-built context (experimental).

    Accepts both ``ToolCallContext`` (no serialization requirement) and
    ``DepsContext`` (with serialization check) for dependency injection.

    Warning:
        This is an experimental feature. The API may change in future versions.

    Args:
        tool: A pydantic-ai Tool object that uses RunContext with deps.
        deps_context: A context object with ``.deps`` property for injection.

    Returns:
        An SdkMcpTool that can be used with Claude Agent SDK.

    Raises:
        TypeError: If the input is not a Tool instance.
    """
    if not isinstance(tool, Tool):
        raise TypeError(f"expected Tool, got {type(tool).__name__}")

    tool_def = tool.tool_def
    name = tool_def.name
    description = tool_def.description or ""
    input_schema = tool_def.parameters_json_schema

    handler = create_async_handler(
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

    Examples:
        >>> from pydantic_ai import Agent
        >>> from pydantic_ai.toolsets.function import FunctionToolset
        >>> agent = Agent("test")
        >>> @agent.tool_plain
        ... def get_weather(city: str) -> str:
        ...     return f"Weather in {city}"
        >>> toolset = agent.toolsets[0]
        >>> assert isinstance(toolset, FunctionToolset)
        >>> tools = list(toolset.tools.values())
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


def convert_mixed_tools_to_mcp_server(
    tools: Sequence[object],
    tools_cache: Mapping[str, object],
    deps_context: ToolCallContext[object] | DepsContext[object] | None = None,
    *,
    server_name: str = "pydantic_tools",
    server_version: str = "1.0.0",
) -> McpSdkServerConfig:
    """Convert a mixed sequence of tools to an MCP server config (experimental).

    Handles both ``takes_ctx`` tools (with deps injection) and plain tools
    in a single pass. For ``takes_ctx`` tools, uses ``convert_tool_with_context()``
    with the pre-built context. For plain tools, uses ``convert_tool()``.
    Falls back to ``convert_tool_definition()`` for non-Tool protocol objects.

    Warning:
        This is an experimental feature. The API may change in future versions.

    Args:
        tools: Sequence of tool objects (Tool instances or PydanticAITool protocol).
        tools_cache: Mapping of tool names to tool objects for ``takes_ctx`` lookup.
        deps_context: Context for ``takes_ctx`` tools. Required if
            any tool has ``takes_ctx=True``.
        server_name: MCP server name. Defaults to ``"pydantic_tools"``.
        server_version: MCP server version. Defaults to ``"1.0.0"``.

    Returns:
        McpSdkServerConfig for use with ClaudeAgentOptions.mcp_servers.
    """
    from claudecode_model.mcp_integration import (
        ToolDefinition,
        convert_tool_definition,
        get_parameters_json_schema,
    )

    sdk_tools: list[SdkMcpTool[JsonSchema]] = []
    for t in tools:
        tool_name = getattr(t, "name", "")
        cached = tools_cache.get(tool_name)
        if (
            cached
            and getattr(cached, "takes_ctx", False) is True
            and isinstance(cached, Tool)
            and deps_context is not None
        ):
            sdk_tools.append(convert_tool_with_context(cached, deps_context))
        elif isinstance(cached, Tool):
            sdk_tools.append(convert_tool(cached))
        else:
            tool_def = ToolDefinition(
                name=tool_name,
                description=getattr(t, "description", ""),
                input_schema=get_parameters_json_schema(t),
                function=getattr(t, "function", None),
            )
            sdk_tools.append(convert_tool_definition(tool_def))

    return create_sdk_mcp_server(
        name=server_name,
        version=server_version,
        tools=sdk_tools if sdk_tools else None,
    )
