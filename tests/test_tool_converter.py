"""Tests for tool_converter module - pydantic-ai Tool to SDK conversion."""

# mypy: disable-error-code="index,operator,arg-type"

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import cast

import httpx
import pytest
from claude_agent_sdk import SdkMcpTool
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from claudecode_model.tool_converter import JsonSchema


# Deps types for serializable deps tests (defined at module level for type resolution)
# Note: Using underscore prefix to avoid pytest collection warnings
@dataclass
class _DictDeps:
    """Dataclass for dict-like deps."""

    api_url: str
    timeout: int


class _ApiConfig(BaseModel):
    """Pydantic model for API config deps."""

    base_url: str
    api_key: str


@dataclass
class _MyDeps:
    """Dataclass for schema test."""

    value: str


def _get_input_schema(tool: SdkMcpTool[JsonSchema]) -> dict[str, object]:
    """Helper to get input_schema as dict for testing."""
    return cast(dict[str, object], tool.input_schema)


async def _call_handler(
    tool: SdkMcpTool[JsonSchema], args: dict[str, object]
) -> dict[str, object]:
    """Helper to call handler with correct types for testing."""
    return cast(dict[str, object], await tool.handler(args))  # type: ignore[arg-type]


class TestConvertToolToSdkMcpTool:
    """Tests for convert_tool function."""

    def test_converts_simple_tool_with_no_args(self) -> None:
        """Tool with no arguments should convert correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def no_args_tool() -> str:
            """A tool with no arguments."""
            return "result"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        assert isinstance(result, SdkMcpTool)
        assert result.name == "no_args_tool"
        assert result.description == "A tool with no arguments."

    def test_converts_tool_with_single_string_arg(self) -> None:
        """Tool with single string argument should convert correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        assert result.name == "greet"
        schema = _get_input_schema(result)
        assert "properties" in schema
        assert "name" in schema["properties"]

    def test_converts_tool_with_multiple_args(self) -> None:
        """Tool with multiple arguments should convert correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def calculate(a: int, b: int, operation: str) -> int:
            """Calculate result of operation."""
            return a + b

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        assert result.name == "calculate"
        schema = _get_input_schema(result)
        assert len(schema["properties"]) == 3
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]
        assert "operation" in schema["properties"]

    def test_preserves_tool_name(self) -> None:
        """Tool name should be preserved in conversion."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def my_special_tool_name(x: str) -> str:
            """Description."""
            return x

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        assert result.name == "my_special_tool_name"

    def test_preserves_tool_description(self) -> None:
        """Tool description should be preserved in conversion."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def tool_with_desc(x: str) -> str:
            """This is a detailed description of what the tool does."""
            return x

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        assert (
            result.description
            == "This is a detailed description of what the tool does."
        )

    def test_handles_none_description(self) -> None:
        """Tool with no description should have empty description."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def no_doc_tool(x: str) -> str:
            return x

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        # Should handle None/empty description gracefully
        assert result.description == "" or result.description is None


class TestSchemaConversion:
    """Tests for JSON schema conversion."""

    def test_converts_simple_properties_schema(self) -> None:
        """Simple properties should be preserved in schema."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def simple_tool(name: str) -> str:
            """Simple tool."""
            return name

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        schema = _get_input_schema(result)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"

    def test_handles_required_fields(self) -> None:
        """Required fields should be marked in schema."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def required_tool(required_arg: str) -> str:
            """Tool with required arg."""
            return required_arg

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        schema = _get_input_schema(result)
        assert "required" in schema
        assert "required_arg" in schema["required"]

    def test_handles_optional_fields(self) -> None:
        """Optional fields should be handled correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def optional_tool(required: str, optional: str | None = None) -> str:
            """Tool with optional arg."""
            return required

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        # required should be in required list, optional should not
        schema = _get_input_schema(result)
        assert "required" in schema["required"]
        # optional may or may not be in required depending on pydantic-ai behavior

    def test_handles_default_values(self) -> None:
        """Fields with defaults should be handled correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def default_tool(name: str, count: int = 10) -> str:
            """Tool with default value."""
            return name

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        # name should be required, count should not be
        schema = _get_input_schema(result)
        assert "name" in schema["required"]


class TestHandlerWrapping:
    """Tests for handler function wrapping."""

    def test_wraps_sync_function(self) -> None:
        """Sync function should be wrapped into async handler."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def sync_tool(msg: str) -> str:
            """Sync tool."""
            return f"received: {msg}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        # Handler should be async
        assert asyncio.iscoroutinefunction(result.handler)

    def test_wraps_async_function(self) -> None:
        """Async function should remain async in handler."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        async def async_tool(msg: str) -> str:
            """Async tool."""
            return f"received: {msg}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        # Handler should be async
        assert asyncio.iscoroutinefunction(result.handler)

    def test_handler_receives_correct_args(self) -> None:
        """Handler should receive arguments correctly."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")
        received_args: dict[str, object] = {}

        @agent.tool_plain
        def capture_tool(city: str, days: int) -> str:
            """Capture args."""
            received_args["city"] = city
            received_args["days"] = days
            return "ok"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        asyncio.run(_call_handler(result, {"city": "Tokyo", "days": 5}))

        assert received_args["city"] == "Tokyo"
        assert received_args["days"] == 5

    def test_handler_returns_mcp_format(self) -> None:
        """Handler should return MCP format response."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def simple_tool(x: str) -> str:
            """Simple."""
            return "result text"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        output: dict[str, object] = asyncio.run(_call_handler(result, {"x": "test"}))

        # Should be MCP format
        assert "content" in output
        assert isinstance(output["content"], list)
        assert len(output["content"]) > 0
        assert output["content"][0]["type"] == "text"


class TestReturnValueConversion:
    """Tests for return value conversion to MCP format."""

    def test_converts_string_to_mcp_text(self) -> None:
        """String return should convert to MCP text format."""
        from claudecode_model.tool_converter import _format_return_value_as_mcp

        result = _format_return_value_as_mcp("hello world")

        assert result == {"content": [{"type": "text", "text": "hello world"}]}

    def test_converts_dict_to_mcp_text_json(self) -> None:
        """Dict return should convert to JSON text in MCP format."""
        from claudecode_model.tool_converter import _format_return_value_as_mcp

        result = _format_return_value_as_mcp({"key": "value", "num": 42})

        assert "content" in result
        assert result["content"][0]["type"] == "text"
        # Should be valid JSON
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == {"key": "value", "num": 42}

    def test_converts_list_to_mcp_text_json(self) -> None:
        """List return should convert to JSON text in MCP format."""
        from claudecode_model.tool_converter import _format_return_value_as_mcp

        result = _format_return_value_as_mcp([1, 2, 3])

        assert "content" in result
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == [1, 2, 3]

    def test_converts_none_to_empty_text(self) -> None:
        """None return should convert to empty text."""
        from claudecode_model.tool_converter import _format_return_value_as_mcp

        result = _format_return_value_as_mcp(None)

        assert result == {"content": [{"type": "text", "text": ""}]}

    def test_preserves_existing_mcp_format(self) -> None:
        """Already MCP format should be returned as-is."""
        from claudecode_model.tool_converter import _format_return_value_as_mcp

        mcp_response: dict[str, object] = {
            "content": [{"type": "text", "text": "existing"}]
        }

        result = _format_return_value_as_mcp(mcp_response)

        assert result == {"content": [{"type": "text", "text": "existing"}]}


class TestErrorHandling:
    """Tests for error handling."""

    def test_raises_on_invalid_tool_type(self) -> None:
        """Invalid tool type should raise TypeError."""
        from claudecode_model.tool_converter import convert_tool

        with pytest.raises(TypeError, match="expected.*Tool"):
            convert_tool("not a tool")  # type: ignore[arg-type]

    def test_raises_on_takes_ctx_true(self) -> None:
        """Tool with takes_ctx=True should raise NotImplementedError."""
        from claudecode_model.tool_converter import convert_tool

        agent: Agent[str] = Agent("test")

        @agent.tool
        def context_tool(ctx: RunContext[str], x: str) -> str:
            """Tool that takes context."""
            return x

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        with pytest.raises(
            NotImplementedError, match="takes_ctx=True are not supported"
        ):
            convert_tool(tool)

    def test_handler_exception_returns_error_format(self) -> None:
        """Handler exception should return error in MCP format."""
        from claudecode_model.tool_converter import convert_tool

        agent = Agent("test")

        @agent.tool_plain
        def failing_tool(x: str) -> str:
            """Always fails."""
            raise ValueError("intentional error")

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        result = convert_tool(tool)

        output: dict[str, object] = asyncio.run(_call_handler(result, {"x": "test"}))

        # Should have error indication in content
        assert "content" in output
        text_content = output["content"][0]["text"]
        assert "error" in text_content.lower() or "intentional error" in text_content


class TestConvertToolsToMcpServer:
    """Tests for convert_tools_to_mcp_server function."""

    def test_creates_mcp_server_config(self) -> None:
        """Should create valid McpServerConfig."""
        from claudecode_model.tool_converter import convert_tools_to_mcp_server

        agent = Agent("test")

        @agent.tool_plain
        def tool1(x: str) -> str:
            """Tool 1."""
            return x

        tools = list(agent._function_toolset.tools.values())

        result = convert_tools_to_mcp_server(
            tools, server_name="test-server", server_version="1.0.0"
        )

        # Should be a dict (McpServerConfig is a TypedDict)
        assert isinstance(result, dict)
        assert result["name"] == "test-server"
        assert result["version"] == "1.0.0"
        assert "tools" in result

    def test_converts_multiple_tools(self) -> None:
        """Multiple tools should all be converted."""
        from claudecode_model.tool_converter import convert_tools_to_mcp_server

        agent = Agent("test")

        @agent.tool_plain
        def tool_a(x: str) -> str:
            """Tool A."""
            return x

        @agent.tool_plain
        def tool_b(y: int) -> int:
            """Tool B."""
            return y

        @agent.tool_plain
        def tool_c(z: bool) -> bool:
            """Tool C."""
            return z

        tools = list(agent._function_toolset.tools.values())

        result = convert_tools_to_mcp_server(
            tools, server_name="multi-server", server_version="1.0.0"
        )

        assert len(result["tools"]) == 3
        tool_names = {t.name for t in result["tools"]}
        assert "tool_a" in tool_names
        assert "tool_b" in tool_names
        assert "tool_c" in tool_names

    def test_handles_empty_tool_list(self) -> None:
        """Empty tool list should create config with no tools."""
        from claudecode_model.tool_converter import convert_tools_to_mcp_server

        result = convert_tools_to_mcp_server(
            [], server_name="empty-server", server_version="1.0.0"
        )

        assert isinstance(result, dict)
        assert result["tools"] == []

    def test_uses_server_name(self) -> None:
        """Server name should be set correctly."""
        from claudecode_model.tool_converter import convert_tools_to_mcp_server

        result = convert_tools_to_mcp_server(
            [], server_name="my-custom-server", server_version="1.0.0"
        )

        assert result["name"] == "my-custom-server"

    def test_uses_server_version(self) -> None:
        """Server version should be set correctly."""
        from claudecode_model.tool_converter import convert_tools_to_mcp_server

        result = convert_tools_to_mcp_server(
            [], server_name="test-server", server_version="2.0.0"
        )

        assert result["version"] == "2.0.0"


class TestSerializableDepsSupport:
    """Tests for serializable dependency support in tool_converter."""

    def test_converts_tool_with_dict_deps(self) -> None:
        """Tool with dict deps should convert and execute correctly."""
        from claudecode_model.tool_converter import convert_tool_with_deps

        agent: Agent[_DictDeps] = Agent("test")
        received_deps: dict[str, object] = {}

        @agent.tool
        def fetch_data(ctx: RunContext[_DictDeps], query: str) -> str:
            """Fetch data using deps."""
            received_deps["api_url"] = ctx.deps.api_url
            received_deps["timeout"] = ctx.deps.timeout
            return f"Fetched: {query}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        deps = _DictDeps(api_url="https://api.example.com", timeout=30)
        result = convert_tool_with_deps(tool, deps)

        assert result.name == "fetch_data"

        # Execute the handler
        output: dict[str, object] = asyncio.run(
            _call_handler(result, {"query": "test query"})
        )

        assert "content" in output
        assert "Fetched: test query" in output["content"][0]["text"]
        assert received_deps["api_url"] == "https://api.example.com"
        assert received_deps["timeout"] == 30

    def test_converts_tool_with_pydantic_model_deps(self) -> None:
        """Tool with Pydantic model deps should convert and execute correctly."""
        from claudecode_model.tool_converter import convert_tool_with_deps

        agent: Agent[_ApiConfig] = Agent("test")
        received_config: dict[str, object] = {}

        @agent.tool
        def call_api(ctx: RunContext[_ApiConfig], endpoint: str) -> str:
            """Call API using config."""
            received_config["base_url"] = ctx.deps.base_url
            received_config["api_key"] = ctx.deps.api_key
            return f"Called: {endpoint}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        config = _ApiConfig(base_url="https://api.example.com", api_key="secret123")
        result = convert_tool_with_deps(tool, config)

        output: dict[str, object] = asyncio.run(
            _call_handler(result, {"endpoint": "/users"})
        )

        assert "Called: /users" in output["content"][0]["text"]
        assert received_config["base_url"] == "https://api.example.com"
        assert received_config["api_key"] == "secret123"

    def test_raises_on_unsupported_deps_type(self) -> None:
        """Unsupported deps type should raise UnsupportedDepsTypeError."""
        from claudecode_model.exceptions import UnsupportedDepsTypeError
        from claudecode_model.tool_converter import convert_tool_with_deps

        agent: Agent[httpx.AsyncClient] = Agent("test")

        @agent.tool
        def use_client(ctx: RunContext[httpx.AsyncClient], url: str) -> str:
            """Use HTTP client."""
            return url

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        client = httpx.AsyncClient()
        try:
            with pytest.raises(UnsupportedDepsTypeError):
                convert_tool_with_deps(tool, client)
        finally:
            asyncio.run(client.aclose())

    def test_tool_with_deps_removes_ctx_from_schema(self) -> None:
        """Tool with deps should not include ctx in the input schema."""
        from claudecode_model.tool_converter import convert_tool_with_deps

        agent: Agent[_MyDeps] = Agent("test")

        @agent.tool
        def my_tool(ctx: RunContext[_MyDeps], name: str, count: int) -> str:
            """Tool with ctx and args."""
            return f"{name}: {count}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        deps = _MyDeps(value="test")
        result = convert_tool_with_deps(tool, deps)

        schema = _get_input_schema(result)
        # ctx should not be in the schema
        assert "ctx" not in schema.get("properties", {})
        # but other args should be
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]

    def test_raises_on_invalid_tool_type_with_deps(self) -> None:
        """convert_tool_with_deps should raise TypeError for non-Tool input."""
        from claudecode_model.tool_converter import convert_tool_with_deps

        with pytest.raises(TypeError, match="expected.*Tool"):
            convert_tool_with_deps("not a tool", {"key": "value"})  # type: ignore[arg-type]

    def test_async_tool_with_deps(self) -> None:
        """Async tool with deps should work correctly."""
        from claudecode_model.tool_converter import convert_tool_with_deps

        agent: Agent[_DictDeps] = Agent("test")
        received_deps: dict[str, object] = {}

        @agent.tool
        async def async_fetch_data(ctx: RunContext[_DictDeps], query: str) -> str:
            """Async fetch data using deps."""
            received_deps["api_url"] = ctx.deps.api_url
            received_deps["timeout"] = ctx.deps.timeout
            return f"Async Fetched: {query}"

        tools = list(agent._function_toolset.tools.values())
        tool = tools[0]

        deps = _DictDeps(api_url="https://async.example.com", timeout=60)
        result = convert_tool_with_deps(tool, deps)

        assert result.name == "async_fetch_data"

        # Execute the async handler
        output: dict[str, object] = asyncio.run(
            _call_handler(result, {"query": "async query"})
        )

        assert "content" in output
        assert "Async Fetched: async query" in output["content"][0]["text"]
        assert received_deps["api_url"] == "https://async.example.com"
        assert received_deps["timeout"] == 60
