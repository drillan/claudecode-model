"""Tests for non-serializable deps support in set_agent_toolsets().

Verifies that tools with takes_ctx=True can be used with non-serializable
dependency objects (e.g., DB connections, custom stores) when called via
the MCP/IPC path.

GitHub Issue context: tools registered with @agent.tool (takes_ctx=True)
whose deps include non-serializable fields (like InsightStore) must still
receive ctx injection when invoked through the IPC handler.
"""

# mypy: disable-error-code="index,operator,arg-type"

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from pydantic_ai import Agent, RunContext

from .conftest import get_agent_tools

from claudecode_model.model import ClaudeCodeModel


@dataclass
class _SerializableDeps:
    """Serializable deps for backward-compat test (must be module-level for get_type_hints)."""

    api_url: str
    timeout: int


class _NonSerializableResource:
    """Simulates a non-serializable dependency like a DB connection or store.

    This is a plain class (not a dataclass, not a BaseModel), so it
    fails DepsContext's is_instance_serializable() check.
    """

    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string
        self._is_open = True

    def query(self, sql: str) -> str:
        return f"result of '{sql}' via {self.connection_string}"


# ---------------------------------------------------------------------------
# ToolCallContext unit tests
# ---------------------------------------------------------------------------


class TestToolCallContext:
    """Tests for ToolCallContext — context wrapper without serialization check."""

    def test_tool_call_context_wraps_non_serializable_deps(self) -> None:
        """ToolCallContext should accept non-serializable objects without raising."""
        from claudecode_model.deps_support import ToolCallContext

        resource = _NonSerializableResource("postgres://localhost/db")
        ctx = ToolCallContext(resource)

        assert ctx.deps is resource
        assert ctx.deps.connection_string == "postgres://localhost/db"

    def test_tool_call_context_wraps_serializable_deps(self) -> None:
        """ToolCallContext should also accept serializable deps."""
        from claudecode_model.deps_support import ToolCallContext

        ctx = ToolCallContext({"api_key": "secret"})
        assert ctx.deps == {"api_key": "secret"}

    def test_tool_call_context_identity(self) -> None:
        """ToolCallContext.deps should return the exact same object (identity)."""
        from claudecode_model.deps_support import ToolCallContext

        resource = _NonSerializableResource("redis://localhost")
        ctx = ToolCallContext(resource)
        assert ctx.deps is resource


# ---------------------------------------------------------------------------
# set_agent_toolsets with non-serializable deps (plain class, NOT dataclass)
# ---------------------------------------------------------------------------


class TestSetAgentToolsetsNonSerializableDeps:
    """Tests for set_agent_toolsets() accepting truly non-serializable deps.

    Uses _NonSerializableResource directly (a plain class, not a dataclass)
    to ensure DepsContext would reject it but ToolCallContext accepts it.
    """

    def test_plain_class_deps_rejected_by_deps_context(self) -> None:
        """Confirm DepsContext rejects plain class instances (precondition)."""
        from claudecode_model.deps_support import DepsContext
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        resource = _NonSerializableResource("postgres://db")
        with pytest.raises(UnsupportedDepsTypeError):
            DepsContext(resource)

    def test_accepts_non_serializable_deps_without_error(self) -> None:
        """set_agent_toolsets should accept non-serializable deps via ToolCallContext."""
        agent: Agent[_NonSerializableResource] = Agent(
            "test", deps_type=_NonSerializableResource
        )

        @agent.tool
        def do_query(ctx: RunContext[_NonSerializableResource], sql: str) -> str:
            """Query using non-serializable store."""
            return ctx.deps.query(sql)

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _NonSerializableResource("postgres://localhost/db")

        # Must NOT raise UnsupportedDepsTypeError
        model.set_agent_toolsets(toolset, deps=deps)

        assert "do_query" in model._tools_cache
        assert model._deps_context is not None
        assert model._deps_context.deps is deps

    def test_ipc_handler_injects_non_serializable_deps(self) -> None:
        """IPC handler should inject non-serializable deps and tool accesses ctx.deps."""
        agent: Agent[_NonSerializableResource] = Agent(
            "test", deps_type=_NonSerializableResource
        )
        received: dict[str, object] = {}

        @agent.tool
        def do_query(ctx: RunContext[_NonSerializableResource], sql: str) -> str:
            """Query using non-serializable store."""
            received["conn"] = ctx.deps.connection_string
            return ctx.deps.query(sql)

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _NonSerializableResource("sqlite:///test.db")

        model.set_agent_toolsets(toolset, deps=deps, transport="stdio")

        assert model._ipc_session is not None
        handler = model._ipc_session._tool_handlers.get("do_query")
        assert handler is not None

        result: dict[str, object] = asyncio.run(handler({"sql": "SELECT 1"}))

        assert "content" in result
        content_list = result["content"]
        assert isinstance(content_list, list)
        assert "result of 'SELECT 1' via sqlite:///test.db" in content_list[0]["text"]
        assert received["conn"] == "sqlite:///test.db"

    def test_sdk_transport_with_non_serializable_deps(self) -> None:
        """SDK transport mode should also work with non-serializable deps."""
        agent: Agent[_NonSerializableResource] = Agent(
            "test", deps_type=_NonSerializableResource
        )

        @agent.tool
        def do_query(ctx: RunContext[_NonSerializableResource], sql: str) -> str:
            """Query using non-serializable store."""
            return ctx.deps.query(sql)

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _NonSerializableResource("postgres://db")

        model.set_agent_toolsets(toolset, deps=deps, transport="sdk")

        assert model._deps_context is not None
        assert model._deps_context.deps is deps

        from claudecode_model.tool_converter import convert_tool_with_context

        tools = get_agent_tools(agent)
        sdk_tool = convert_tool_with_context(tools[0], model._deps_context)
        result: dict[str, object] = asyncio.run(sdk_tool.handler({"sql": "SELECT 1"}))

        assert "content" in result
        content_list = result["content"]
        assert isinstance(content_list, list)
        assert "result of 'SELECT 1' via postgres://db" in content_list[0]["text"]

    def test_deps_object_is_shared_by_reference(self) -> None:
        """Mutations to deps object should be visible to tool handlers (shared reference)."""
        agent: Agent[_NonSerializableResource] = Agent(
            "test", deps_type=_NonSerializableResource
        )

        @agent.tool
        def check_open(ctx: RunContext[_NonSerializableResource]) -> str:
            """Check if resource is open."""
            return f"open={ctx.deps._is_open}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _NonSerializableResource("postgres://db")
        deps._is_open = True

        model.set_agent_toolsets(toolset, deps=deps, transport="stdio")

        assert model._ipc_session is not None
        handler = model._ipc_session._tool_handlers.get("check_open")
        assert handler is not None

        # Mutate deps after registration
        deps._is_open = False

        result: dict[str, object] = asyncio.run(handler({}))
        # Handler should see the updated value
        assert "open=False" in result["content"][0]["text"]

    def test_missing_deps_still_raises_error(self) -> None:
        """takes_ctx tools without deps should still raise MissingDepsError."""
        from claudecode_model.exceptions import MissingDepsError

        agent: Agent[_NonSerializableResource] = Agent(
            "test", deps_type=_NonSerializableResource
        )

        @agent.tool
        def do_query(ctx: RunContext[_NonSerializableResource], sql: str) -> str:
            """Query."""
            return sql

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]

        with pytest.raises(MissingDepsError) as exc_info:
            model.set_agent_toolsets(toolset)

        assert "do_query" in exc_info.value.tool_names

    def test_backward_compat_serializable_deps(self) -> None:
        """Serializable deps should continue to work exactly as before."""
        agent: Agent[_SerializableDeps] = Agent("test", deps_type=_SerializableDeps)

        @agent.tool
        async def fetch(ctx: RunContext[_SerializableDeps], q: str) -> str:
            """Fetch data."""
            return f"url={ctx.deps.api_url}, q={q}"

        model = ClaudeCodeModel()
        toolset = agent.toolsets[0]
        deps = _SerializableDeps(api_url="https://api.example.com", timeout=30)

        model.set_agent_toolsets(toolset, deps=deps, transport="stdio")

        assert model._ipc_session is not None
        handler = model._ipc_session._tool_handlers.get("fetch")
        assert handler is not None

        result: dict[str, object] = asyncio.run(handler({"q": "test"}))
        assert "url=https://api.example.com, q=test" in result["content"][0]["text"]
