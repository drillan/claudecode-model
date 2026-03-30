"""Tests for set_agent_toolsets() with deps parameter (takes_ctx support).

Tests that set_agent_toolsets() correctly handles tools with takes_ctx=True
by injecting DepsContext when deps are provided.
"""

# mypy: disable-error-code="index,operator,arg-type"

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic_ai import Agent, RunContext

from .conftest import get_agent_tools

from claudecode_model.exceptions import MissingDepsError, UnsupportedDepsTypeError
from claudecode_model.model import ClaudeCodeModel


@dataclass
class _TestDeps:
    """Dataclass for test dependencies."""

    api_url: str
    timeout: int


def _create_plain_mock_tool(name: str = "plain_tool") -> MagicMock:
    """Create a mock tool without takes_ctx (plain tool)."""

    async def dummy_func(**kwargs: object) -> str:
        return "plain result"

    mock = MagicMock()
    mock.name = name
    mock.description = f"A plain tool: {name}"
    mock.parameters_json_schema = {"type": "object", "properties": {}}
    mock.function = dummy_func
    mock.takes_ctx = False
    return mock


class TestSetAgentToolsetsWithDeps:
    """Tests for set_agent_toolsets() with deps parameter."""

    def test_set_agent_toolsets_with_takes_ctx_and_deps(self) -> None:
        """set_agent_toolsets should accept deps for takes_ctx tools."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)

        @agent.tool
        def fetch_data(ctx: RunContext[_TestDeps], query: str) -> str:
            """Fetch data using deps."""
            return f"url={ctx.deps.api_url}, query={query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _TestDeps(api_url="https://api.example.com", timeout=30)

        # Should not raise
        model.set_agent_toolsets(toolset, deps=deps)

        assert model._agent_toolsets is not None
        assert "fetch_data" in model._tools_cache
        assert model._deps_context is not None
        assert model._deps_context.deps is deps

    def test_set_agent_toolsets_raises_missing_deps_error(self) -> None:
        """set_agent_toolsets should raise MissingDepsError for takes_ctx tools without deps."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)

        @agent.tool
        def fetch_data(ctx: RunContext[_TestDeps], query: str) -> str:
            """Fetch data using deps."""
            return f"query={query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]

        with pytest.raises(MissingDepsError) as exc_info:
            model.set_agent_toolsets(toolset)

        assert "fetch_data" in exc_info.value.tool_names
        assert "deps" in str(exc_info.value)

    def test_set_agent_toolsets_mixed_tools_with_deps(self) -> None:
        """set_agent_toolsets should handle mixed takes_ctx and plain tools."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)

        @agent.tool
        def ctx_tool(ctx: RunContext[_TestDeps], query: str) -> str:
            """Tool with context."""
            return f"url={ctx.deps.api_url}"

        @agent.tool_plain
        def plain_tool(query: str) -> str:
            """Tool without context."""
            return f"plain: {query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _TestDeps(api_url="https://api.example.com", timeout=30)

        # Should not raise — both tools registered
        model.set_agent_toolsets(toolset, deps=deps)

        assert "ctx_tool" in model._tools_cache
        assert "plain_tool" in model._tools_cache

    def test_set_agent_toolsets_plain_tools_no_deps(self) -> None:
        """set_agent_toolsets should work with plain tools and no deps (backward compat)."""
        model = ClaudeCodeModel()
        mock_tool = _create_plain_mock_tool()

        # Should not raise — no takes_ctx tools, no deps needed
        model.set_agent_toolsets([mock_tool])

        assert "plain_tool" in model._tools_cache
        assert model._deps_context is None

    def test_set_agent_toolsets_with_unsupported_deps_type(self) -> None:
        """set_agent_toolsets should raise UnsupportedDepsTypeError for non-serializable deps."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)

        @agent.tool
        def fetch_data(ctx: RunContext[_TestDeps], query: str) -> str:
            """Fetch data using deps."""
            return f"query={query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]

        # httpx.AsyncClient is not serializable
        with pytest.raises(UnsupportedDepsTypeError):
            model.set_agent_toolsets(toolset, deps=httpx.AsyncClient())

    def test_ipc_handler_injects_deps_context(self) -> None:
        """IPC handler should inject DepsContext for takes_ctx tools (stdio mode)."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)
        received_deps: dict[str, object] = {}

        @agent.tool
        def fetch_data(ctx: RunContext[_TestDeps], query: str) -> str:
            """Fetch data using deps."""
            received_deps["api_url"] = ctx.deps.api_url
            received_deps["timeout"] = ctx.deps.timeout
            return f"Fetched: {query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _TestDeps(api_url="https://api.example.com", timeout=30)

        model.set_agent_toolsets(toolset, deps=deps, transport="stdio")

        # Verify IPC session was created with handler
        assert model._ipc_session is not None
        handler = model._ipc_session._tool_handlers.get("fetch_data")
        assert handler is not None

        # Execute the handler and verify deps injection
        result: dict[str, object] = asyncio.run(handler({"query": "test query"}))

        assert "content" in result
        content_list = result["content"]
        assert isinstance(content_list, list)
        assert len(content_list) > 0
        assert "Fetched: test query" in content_list[0]["text"]
        assert received_deps["api_url"] == "https://api.example.com"
        assert received_deps["timeout"] == 30

    def test_set_agent_toolsets_deps_with_sdk_transport(self) -> None:
        """set_agent_toolsets should work with deps in SDK transport mode and handler executes."""
        agent: Agent[_TestDeps] = Agent("test", deps_type=_TestDeps)
        received_deps: dict[str, object] = {}

        @agent.tool
        def fetch_data(ctx: RunContext[_TestDeps], query: str) -> str:
            """Fetch data using deps."""
            received_deps["api_url"] = ctx.deps.api_url
            received_deps["timeout"] = ctx.deps.timeout
            return f"url={ctx.deps.api_url}, query={query}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _TestDeps(api_url="https://api.example.com", timeout=30)

        # Should not raise in SDK mode
        model.set_agent_toolsets(toolset, deps=deps, transport="sdk")

        assert model._agent_toolsets is not None
        assert "fetch_data" in model._tools_cache
        assert model._deps_context is not None
        assert model._deps_context.deps is deps

        # Verify handler execution via convert_tool_with_context (same path as SDK mode)
        from claudecode_model.tool_converter import convert_tool_with_context

        tools = get_agent_tools(agent)
        sdk_tool = convert_tool_with_context(tools[0], model._deps_context)
        result: dict[str, object] = asyncio.run(sdk_tool.handler({"query": "test"}))

        assert "content" in result
        content_list = result["content"]
        assert isinstance(content_list, list)
        assert "url=https://api.example.com, query=test" in content_list[0]["text"]
        assert received_deps["api_url"] == "https://api.example.com"
        assert received_deps["timeout"] == 30
