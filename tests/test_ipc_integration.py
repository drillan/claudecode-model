"""Tests for IPC lifecycle management (US2: Phase 5) and transport selection (US3: Phase 6).

TDD Red phase: These tests MUST fail before implementation.

T019: IPC lifecycle tests — auto-start/stop in request(), stream_messages(),
      request_with_metadata(), cleanup on exception, stale socket detection,
      multiple sequential requests.

T024: Transport selection tests — transport="stdio" → McpStdioServerConfig,
      transport="sdk" → McpSdkServerConfig (existing behavior),
      transport="auto" → McpStdioServerConfig (stdio equivalent),
      default transport is "auto",
      _process_function_tools() preserves transport mode.
"""

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk.types import Message
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from claudecode_model.exceptions import CLIExecutionError
from claudecode_model.ipc import DEFAULT_TRANSPORT
from claudecode_model.ipc.protocol import (
    SOCKET_FILE_PREFIX,
    SOCKET_FILE_SUFFIX,
    SOCKET_PERMISSIONS,
    ToolSchema,
)
from claudecode_model.ipc.server import IPCSession
from claudecode_model.mcp_integration import MCP_SERVER_NAME
from claudecode_model.model import ClaudeCodeModel

from .conftest import create_mock_result_message


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_messages(prompt: str = "hello") -> list[ModelMessage]:
    """Create a minimal list of ModelMessage with a user prompt."""
    return [ModelRequest(parts=[UserPromptPart(content=prompt)])]


def _create_model_with_ipc_session() -> tuple[ClaudeCodeModel, IPCSession]:
    """Create a ClaudeCodeModel with a mock IPC session.

    Returns a model with an IPCSession that has mock start/stop methods
    so we can verify lifecycle calls without actually starting a server.
    """
    model = ClaudeCodeModel()

    # Create a real IPCSession but mock its start/stop
    schemas: list[ToolSchema] = [
        {"name": "test_tool", "description": "A test tool", "input_schema": {}},
    ]

    async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
        return {"content": [{"type": "text", "text": "ok"}]}

    session = IPCSession(
        tool_handlers={"test_tool": dummy_handler},
        tool_schemas=schemas,
    )
    session.start = AsyncMock()  # type: ignore[method-assign]
    session.stop = AsyncMock()  # type: ignore[method-assign]

    model._ipc_session = session
    return model, session


def _mock_model_request_parameters() -> MagicMock:
    """Create a mock ModelRequestParameters."""
    params = MagicMock()
    params.function_tools = []
    params.output_mode = "text"
    params.output_object = None
    return params


def _create_stale_socket(tmp_dir: str | None = None) -> Path:
    """Create a stale socket file in the temp directory.

    Returns the path to the created file.
    """
    target_dir = tmp_dir or tempfile.gettempdir()
    stale_path = (
        Path(target_dir) / f"{SOCKET_FILE_PREFIX}stale_test_id{SOCKET_FILE_SUFFIX}"
    )
    stale_path.touch()
    return stale_path


# ── T019: IPC Lifecycle in request() ──────────────────────────────────────


class TestIPCAutoStartInRequest:
    """IPC server auto-starts before SDK query in request()."""

    @pytest.mark.asyncio
    async def test_ipc_server_starts_before_query(self) -> None:
        """IPCSession.start() is called before the SDK query executes."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = MagicMock(
                result_message=result_msg,
                captured_structured_output_input=None,
            )
            await model.request(_make_messages(), None, params)

        session.start.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_ipc_server_stops_after_query(self) -> None:
        """IPCSession.stop() is called after request() completes."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = MagicMock(
                result_message=result_msg,
                captured_structured_output_input=None,
            )
            await model.request(_make_messages(), None, params)

        session.stop.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_no_ipc_lifecycle_when_session_is_none(self) -> None:
        """When no IPC session is configured, request() works normally."""
        model = ClaudeCodeModel()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        assert model._ipc_session is None

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = MagicMock(
                result_message=result_msg,
                captured_structured_output_input=None,
            )
            await model.request(_make_messages(), None, params)

        # Should complete without error even without IPC session


# ── T019: Cleanup on Exception ────────────────────────────────────────────


class TestIPCCleanupOnException:
    """IPC server is stopped even when exceptions occur (try/finally)."""

    @pytest.mark.asyncio
    async def test_cleanup_on_request_exception(self) -> None:
        """IPCSession.stop() is called when _execute_request raises."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.side_effect = CLIExecutionError(
                "Test error",
                exit_code=1,
                stderr="error",
                error_type="unknown",
                recoverable=False,
            )
            with pytest.raises(CLIExecutionError):
                await model.request(_make_messages(), None, params)

        session.stop.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_cleanup_on_request_with_metadata_exception(self) -> None:
        """IPCSession.stop() is called when request_with_metadata raises."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.side_effect = CLIExecutionError(
                "Test error",
                exit_code=1,
                stderr="error",
                error_type="unknown",
                recoverable=False,
            )
            with pytest.raises(CLIExecutionError):
                await model.request_with_metadata(_make_messages(), None, params)

        session.stop.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_socket_and_schema_deleted_on_exception(self) -> None:
        """Socket file and schema file are deleted when exception occurs.

        Uses a real IPCSession (not mocked) to verify file cleanup.
        """
        model = ClaudeCodeModel()
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )
        model._ipc_session = session

        # Write schema file (simulating _prepare_ipc_session behavior)
        session._write_schema_file()
        assert Path(session.schema_path).exists()

        params = _mock_model_request_parameters()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.side_effect = CLIExecutionError(
                "Test error",
                exit_code=1,
                stderr="error",
                error_type="unknown",
                recoverable=False,
            )
            with pytest.raises(CLIExecutionError):
                await model.request(_make_messages(), None, params)

        # Both files should be cleaned up
        assert not Path(session.socket_path).exists()
        assert not Path(session.schema_path).exists()


# ── T019: IPC Lifecycle in request_with_metadata() ────────────────────────


class TestIPCLifecycleInRequestWithMetadata:
    """IPC server auto-starts/stops in request_with_metadata()."""

    @pytest.mark.asyncio
    async def test_ipc_start_stop_in_request_with_metadata(self) -> None:
        """IPCSession.start() and stop() are called around query."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = MagicMock(
                result_message=result_msg,
                captured_structured_output_input=None,
            )
            await model.request_with_metadata(_make_messages(), None, params)

        session.start.assert_called_once()  # type: ignore[attr-defined]
        session.stop.assert_called_once()  # type: ignore[attr-defined]


# ── T019: IPC Lifecycle in stream_messages() ──────────────────────────────


class TestIPCLifecycleInStreamMessages:
    """IPC server auto-starts/stops in stream_messages()."""

    @pytest.mark.asyncio
    async def test_ipc_starts_before_streaming(self) -> None:
        """IPCSession.start() is called before streaming begins."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        async def fake_query(**kwargs: object) -> AsyncIterator[Message]:
            yield result_msg  # type: ignore[misc]

        with patch("claudecode_model.model.query", side_effect=fake_query):
            async for _ in model.stream_messages(_make_messages(), None, params):
                pass

        session.start.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_ipc_stops_after_streaming_completes(self) -> None:
        """IPCSession.stop() is called after streaming finishes."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        async def fake_query(**kwargs: object) -> AsyncIterator[Message]:
            yield result_msg  # type: ignore[misc]

        with patch("claudecode_model.model.query", side_effect=fake_query):
            async for _ in model.stream_messages(_make_messages(), None, params):
                pass

        session.stop.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_ipc_stops_on_streaming_exception(self) -> None:
        """IPCSession.stop() is called even when streaming raises."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()

        async def failing_query(**kwargs: object) -> AsyncIterator[Message]:
            raise RuntimeError("Stream failed")
            yield  # type: ignore[misc]  # Make it a generator

        with patch("claudecode_model.model.query", side_effect=failing_query):
            with pytest.raises(CLIExecutionError):
                async for _ in model.stream_messages(_make_messages(), None, params):
                    pass

        session.stop.assert_called_once()  # type: ignore[attr-defined]


# ── T019: Stale Socket Detection ──────────────────────────────────────────


class TestStaleSocketDetection:
    """Stale socket files from previous crashes are detected and removed."""

    @pytest.mark.asyncio
    async def test_stale_socket_removed_on_start(self) -> None:
        """start() removes stale socket files before starting."""
        stale_path = _create_stale_socket()
        assert stale_path.exists()

        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            # Stale socket should be removed
            assert not stale_path.exists()
            # New session's socket should exist
            assert Path(session.socket_path).exists()
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_own_socket_not_removed_as_stale(self) -> None:
        """start() does not remove its own socket file."""
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            # Own socket must exist
            assert Path(session.socket_path).exists()
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_multiple_stale_sockets_removed(self) -> None:
        """start() removes all stale socket files, not just one."""
        stale1 = _create_stale_socket()
        # Create another stale socket with different name
        stale2 = (
            Path(tempfile.gettempdir())
            / f"{SOCKET_FILE_PREFIX}another_stale{SOCKET_FILE_SUFFIX}"
        )
        stale2.touch()

        assert stale1.exists()
        assert stale2.exists()

        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            assert not stale1.exists()
            assert not stale2.exists()
        finally:
            await session.stop()


# ── T019: Multiple Sequential Requests ────────────────────────────────────


class TestMultipleSequentialRequests:
    """Multiple sequential requests with IPC lifecycle succeed."""

    @pytest.mark.asyncio
    async def test_two_sequential_requests_succeed(self) -> None:
        """Two sequential request() calls each start/stop the IPC session."""
        model, session = _create_model_with_ipc_session()
        params = _mock_model_request_parameters()
        result_msg = create_mock_result_message()

        with patch.object(
            model, "_execute_sdk_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = MagicMock(
                result_message=result_msg,
                captured_structured_output_input=None,
            )
            messages = _make_messages()
            await model.request(messages, None, params)
            await model.request(messages, None, params)

        assert session.start.call_count == 2  # type: ignore[attr-defined]
        assert session.stop.call_count == 2  # type: ignore[attr-defined]


# ── T023: Socket File Permissions ─────────────────────────────────────────


class TestSocketFilePermissions:
    """Socket file permissions are set to 0o600 after server bind."""

    @pytest.mark.asyncio
    async def test_socket_permissions_are_owner_only(self) -> None:
        """Socket file has 0o600 permissions after start()."""
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            mode = os.stat(session.socket_path).st_mode & 0o777
            assert mode == SOCKET_PERMISSIONS
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_schema_permissions_are_owner_only(self) -> None:
        """Schema file has 0o600 permissions after start()."""
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy_handler(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy_handler},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            mode = os.stat(session.schema_path).st_mode & 0o777
            assert mode == SOCKET_PERMISSIONS
        finally:
            await session.stop()


# ── Helpers for US3 Transport Selection ────────────────────────────────


def _create_mock_tool(name: str = "my_tool") -> MagicMock:
    """Create a mock PydanticAITool for transport selection tests."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Description of {name}"
    tool.parameters_json_schema = {"type": "object", "properties": {}}

    async def fake_fn(**kwargs: object) -> str:
        return "result"

    tool.function = fake_fn
    return tool


# ── T024: Transport Selection — transport="stdio" ─────────────────────


class TestTransportStdio:
    """transport="stdio" produces McpStdioServerConfig (type="stdio")."""

    def test_stdio_creates_stdio_config(self) -> None:
        """set_agent_toolsets(transport="stdio") stores config with type="stdio"."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="stdio")

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"

    def test_stdio_creates_ipc_session(self) -> None:
        """transport="stdio" creates an IPCSession on the model."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="stdio")

        assert model._ipc_session is not None
        assert isinstance(model._ipc_session, IPCSession)

    def test_stdio_config_points_to_bridge(self) -> None:
        """McpStdioServerConfig args include bridge module path."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="stdio")

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"
        assert "claudecode_model.ipc.bridge" in config["args"]


# ── T024: Transport Selection — transport="sdk" ───────────────────────


class TestTransportSdk:
    """transport="sdk" produces McpSdkServerConfig (existing behavior)."""

    def test_sdk_creates_sdk_config(self) -> None:
        """set_agent_toolsets(transport="sdk") stores config with type="sdk"."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="sdk")

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "sdk"

    def test_sdk_does_not_create_ipc_session(self) -> None:
        """transport="sdk" does not create an IPCSession."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="sdk")

        assert model._ipc_session is None


# ── T024: Transport Selection — transport="auto" ──────────────────────


class TestTransportAuto:
    """transport="auto" is equivalent to "stdio"."""

    def test_auto_creates_stdio_config(self) -> None:
        """set_agent_toolsets(transport="auto") stores config with type="stdio"."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="auto")

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"

    def test_auto_creates_ipc_session(self) -> None:
        """transport="auto" creates an IPCSession like "stdio"."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool], transport="auto")

        assert model._ipc_session is not None


# ── T024: Transport Selection — default transport ─────────────────────


class TestTransportDefault:
    """Default transport is "auto"."""

    def test_default_transport_is_auto(self) -> None:
        """DEFAULT_TRANSPORT constant is "auto"."""
        assert DEFAULT_TRANSPORT == "auto"

    def test_default_transport_creates_stdio_config(self) -> None:
        """set_agent_toolsets() without transport creates config with type="stdio"."""
        model = ClaudeCodeModel()
        tool = _create_mock_tool()
        model.set_agent_toolsets([tool])

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"


# ── T024/T026: _process_function_tools() preserves transport mode ─────


class TestProcessFunctionToolsTransportPreservation:
    """_process_function_tools() re-creates the correct config type per transport."""

    def test_stdio_preserved_after_tool_filtering(self) -> None:
        """After _process_function_tools(), stdio transport still produces
        config with type="stdio" (not type="sdk")."""
        model = ClaudeCodeModel()
        tool1 = _create_mock_tool("tool_a")
        tool2 = _create_mock_tool("tool_b")
        model.set_agent_toolsets([tool1, tool2], transport="stdio")

        # Simulate pydantic-ai passing a subset of tools via function_tools
        tool_def = MagicMock()
        tool_def.name = "tool_a"
        model._process_function_tools([tool_def])

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"

    def test_sdk_preserved_after_tool_filtering(self) -> None:
        """After _process_function_tools(), sdk transport still produces
        config with type="sdk"."""
        model = ClaudeCodeModel()
        tool1 = _create_mock_tool("tool_a")
        tool2 = _create_mock_tool("tool_b")
        model.set_agent_toolsets([tool1, tool2], transport="sdk")

        tool_def = MagicMock()
        tool_def.name = "tool_a"
        model._process_function_tools([tool_def])

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "sdk"

    def test_auto_preserved_after_tool_filtering(self) -> None:
        """After _process_function_tools(), auto transport still produces
        config with type="stdio"."""
        model = ClaudeCodeModel()
        tool1 = _create_mock_tool("tool_a")
        tool2 = _create_mock_tool("tool_b")
        model.set_agent_toolsets([tool1, tool2], transport="auto")

        tool_def = MagicMock()
        tool_def.name = "tool_a"
        model._process_function_tools([tool_def])

        servers = model.get_mcp_servers()
        config = servers[MCP_SERVER_NAME]
        assert config["type"] == "stdio"

    def test_ipc_session_regenerated_after_filtering(self) -> None:
        """After _process_function_tools() in stdio mode, a new IPCSession
        is created for the filtered tool set."""
        model = ClaudeCodeModel()
        tool1 = _create_mock_tool("tool_a")
        tool2 = _create_mock_tool("tool_b")
        model.set_agent_toolsets([tool1, tool2], transport="stdio")

        original_session = model._ipc_session
        assert original_session is not None

        tool_def = MagicMock()
        tool_def.name = "tool_a"
        model._process_function_tools([tool_def])

        new_session = model._ipc_session
        assert new_session is not None
        # New session should be a different object (regenerated)
        assert new_session is not original_session

    def test_sdk_no_ipc_session_after_filtering(self) -> None:
        """After _process_function_tools() in sdk mode, no IPCSession exists."""
        model = ClaudeCodeModel()
        tool1 = _create_mock_tool("tool_a")
        tool2 = _create_mock_tool("tool_b")
        model.set_agent_toolsets([tool1, tool2], transport="sdk")

        assert model._ipc_session is None

        tool_def = MagicMock()
        tool_def.name = "tool_a"
        model._process_function_tools([tool_def])

        assert model._ipc_session is None
