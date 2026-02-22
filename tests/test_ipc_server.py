"""Tests for IPC server (IPCServer and IPCSession).

TDD Red phase: These tests MUST fail before implementation.

T012: IPCServer tests — Unix socket bind/accept, call_tool dispatch,
      result/error responses, unknown tool handling.
T013: IPCSession tests — lifecycle, socket path generation, schema file creation.
"""

import asyncio
import json
import os
import struct
import tempfile
import uuid
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest

from claudecode_model.exceptions import IPCToolExecutionError
from claudecode_model.ipc.protocol import (
    SCHEMA_FILE_PREFIX,
    SOCKET_FILE_PREFIX,
    SOCKET_FILE_SUFFIX,
    SOCKET_PERMISSIONS,
    ToolSchema,
)
from claudecode_model.ipc.server import IPCServer, IPCSession, ToolHandler


# ── Helpers ───────────────────────────────────────────────────────────────


async def _send_ipc_request(
    socket_path: str, method: str, params: dict[str, object]
) -> dict[str, object]:
    """Send a length-prefixed IPC request and return the response."""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        request = {"method": method, "params": params}
        payload = json.dumps(request).encode("utf-8")
        prefix = struct.pack("!I", len(payload))
        writer.write(prefix + payload)
        await writer.drain()

        # Read response
        resp_prefix = await reader.readexactly(4)
        (resp_length,) = struct.unpack("!I", resp_prefix)
        resp_payload = await reader.readexactly(resp_length)
        return json.loads(resp_payload.decode("utf-8"))
    finally:
        writer.close()
        await writer.wait_closed()


def _mock_handler(
    return_value: dict[str, object] | None = None,
    side_effect: Exception | None = None,
) -> AsyncMock:
    """Create an AsyncMock that satisfies ToolHandler type."""
    kwargs: dict[str, object] = {}
    if return_value is not None:
        kwargs["return_value"] = return_value
    if side_effect is not None:
        kwargs["side_effect"] = side_effect
    return AsyncMock(**kwargs)


def _handlers(*pairs: tuple[str, AsyncMock]) -> dict[str, ToolHandler]:
    """Build a typed handler dict from (name, mock) pairs."""
    return {name: cast(ToolHandler, mock) for name, mock in pairs}


def _result(response: dict[str, object]) -> dict[str, object]:
    """Extract the 'result' dict from an IPC response (typed helper)."""
    r = response["result"]
    assert isinstance(r, dict)
    return r


def _error(response: dict[str, object]) -> dict[str, object]:
    """Extract the 'error' dict from an IPC response (typed helper)."""
    e = response["error"]
    assert isinstance(e, dict)
    return e


# ── T012: IPCServer Tests ────────────────────────────────────────────────


class TestIPCServerBindAccept:
    """IPCServer should bind to a Unix socket and accept connections."""

    @pytest.mark.asyncio
    async def test_server_binds_to_socket_path(self, tmp_path: Path) -> None:
        """Server creates a Unix socket file at the specified path."""
        socket_path = tmp_path / "test.sock"
        server = IPCServer(str(socket_path), {})

        await server.start()
        try:
            assert socket_path.exists()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_server_accepts_connection(self, tmp_path: Path) -> None:
        """Server accepts a client connection without error."""
        socket_path = tmp_path / "test.sock"
        mock = _mock_handler(return_value={"content": [{"type": "text", "text": "ok"}]})
        server = IPCServer(str(socket_path), _handlers(("test_tool", mock)))

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "test_tool", "arguments": {}},
            )
            assert "result" in response
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_socket_removed_after_stop(self, tmp_path: Path) -> None:
        """Socket file is removed when server stops."""
        socket_path = tmp_path / "test.sock"
        server = IPCServer(str(socket_path), {})

        await server.start()
        assert socket_path.exists()
        await server.stop()
        assert not socket_path.exists()


class TestIPCServerCallToolDispatch:
    """IPCServer dispatches call_tool requests to registered handlers."""

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_handler(self, tmp_path: Path) -> None:
        """call_tool dispatches to the handler matching the tool name."""
        socket_path = tmp_path / "test.sock"
        mock_a = _mock_handler(
            return_value={"content": [{"type": "text", "text": "result_a"}]}
        )
        mock_b = _mock_handler(
            return_value={"content": [{"type": "text", "text": "result_b"}]}
        )
        server = IPCServer(
            str(socket_path), _handlers(("tool_a", mock_a), ("tool_b", mock_b))
        )

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "tool_b", "arguments": {"x": 1}},
            )
            mock_b.assert_called_once_with({"x": 1})
            mock_a.assert_not_called()
            result = _result(response)
            assert result["content"][0]["text"] == "result_b"  # type: ignore[index]
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_passes_arguments_to_handler(self, tmp_path: Path) -> None:
        """call_tool passes the arguments dict to the handler."""
        socket_path = tmp_path / "test.sock"
        mock = _mock_handler(return_value={"content": [{"type": "text", "text": "ok"}]})
        server = IPCServer(str(socket_path), _handlers(("my_tool", mock)))

        await server.start()
        try:
            await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "my_tool", "arguments": {"key": "value", "num": 42}},
            )
            mock.assert_called_once_with({"key": "value", "num": 42})
        finally:
            await server.stop()


class TestIPCServerToolResult:
    """IPCServer returns tool execution results as IPCResponse."""

    @pytest.mark.asyncio
    async def test_returns_success_result(self, tmp_path: Path) -> None:
        """Successful tool execution returns IPCResponse with result."""
        socket_path = tmp_path / "test.sock"
        mock = _mock_handler(
            return_value={
                "content": [{"type": "text", "text": "hello world"}],
            }
        )
        server = IPCServer(str(socket_path), _handlers(("greet", mock)))

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "greet", "arguments": {}},
            )
            result = _result(response)
            assert result["content"] == [{"type": "text", "text": "hello world"}]
        finally:
            await server.stop()


class TestIPCServerErrorResponse:
    """IPCServer returns errors as IPCErrorResponse."""

    @pytest.mark.asyncio
    async def test_handler_exception_returns_error_response(
        self, tmp_path: Path
    ) -> None:
        """When handler raises, server returns IPCErrorResponse."""
        socket_path = tmp_path / "test.sock"
        mock = _mock_handler(side_effect=ValueError("bad input"))
        server = IPCServer(str(socket_path), _handlers(("fail_tool", mock)))

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "fail_tool", "arguments": {}},
            )
            error = _error(response)
            assert "bad input" in str(error["message"])
            assert error["type"] == "ValueError"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_response(self, tmp_path: Path) -> None:
        """Requesting an unregistered tool returns IPCErrorResponse."""
        socket_path = tmp_path / "test.sock"
        server = IPCServer(str(socket_path), {})

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "nonexistent", "arguments": {}},
            )
            error = _error(response)
            assert "nonexistent" in str(error["message"])
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_ipc_tool_execution_error_preserves_type(
        self, tmp_path: Path
    ) -> None:
        """IPCToolExecutionError from handler is reflected in error type."""
        socket_path = tmp_path / "test.sock"
        mock = _mock_handler(side_effect=IPCToolExecutionError("tool crashed"))
        server = IPCServer(str(socket_path), _handlers(("crash_tool", mock)))

        await server.start()
        try:
            response = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "crash_tool", "arguments": {}},
            )
            error = _error(response)
            assert "tool crashed" in str(error["message"])
            assert error["type"] == "IPCToolExecutionError"
        finally:
            await server.stop()


class TestIPCServerMultipleRequests:
    """IPCServer handles multiple sequential connections."""

    @pytest.mark.asyncio
    async def test_handles_multiple_sequential_requests(self, tmp_path: Path) -> None:
        """Server handles multiple requests on separate connections."""
        socket_path = tmp_path / "test.sock"
        call_count = 0

        async def counting_handler(args: dict[str, object]) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"content": [{"type": "text", "text": f"call_{call_count}"}]}

        server = IPCServer(str(socket_path), {"counter": counting_handler})

        await server.start()
        try:
            r1 = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "counter", "arguments": {}},
            )
            r2 = await _send_ipc_request(
                str(socket_path),
                "call_tool",
                {"name": "counter", "arguments": {}},
            )
            result1 = _result(r1)
            result2 = _result(r2)
            assert result1["content"][0]["text"] == "call_1"  # type: ignore[index]
            assert result2["content"][0]["text"] == "call_2"  # type: ignore[index]
            assert call_count == 2
        finally:
            await server.stop()


# ── T013: IPCSession Tests ───────────────────────────────────────────────


class TestIPCSessionLifecycle:
    """IPCSession create/start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_create_session_sets_paths(self) -> None:
        """IPCSession constructor sets socket_path and schema_path."""
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]
        session = IPCSession(tool_handlers={}, tool_schemas=schemas)

        assert session.socket_path is not None
        assert session.schema_path is not None

    @pytest.mark.asyncio
    async def test_start_creates_socket_and_schema(self) -> None:
        """start() creates socket file and schema file."""
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
            assert Path(session.socket_path).exists()
            assert Path(session.schema_path).exists()
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_stop_removes_socket_and_schema(self) -> None:
        """stop() removes socket file and schema file."""
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
        socket_path = session.socket_path
        schema_path = session.schema_path

        await session.stop()
        assert not Path(socket_path).exists()
        assert not Path(schema_path).exists()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        """stop() can be called multiple times without error."""
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
        await session.stop()
        await session.stop()  # Should not raise


class TestIPCSessionSocketPath:
    """IPCSession socket path generation with UUID."""

    def test_socket_path_contains_uuid(self) -> None:
        """Socket path contains a UUID segment for uniqueness."""
        session = IPCSession(tool_handlers={}, tool_schemas=[])
        path = Path(session.socket_path)

        assert path.name.startswith(SOCKET_FILE_PREFIX)
        assert path.name.endswith(SOCKET_FILE_SUFFIX)

        # Extract UUID portion from filename
        # Format: claudecode_ipc_<uuid>.sock
        stem = path.stem  # claudecode_ipc_<uuid>
        uuid_part = stem[len(SOCKET_FILE_PREFIX) :]
        # Validate it's a valid hex UUID
        uuid.UUID(uuid_part)  # Raises ValueError if invalid

    def test_socket_path_in_temp_directory(self) -> None:
        """Socket path is in the system temp directory."""
        session = IPCSession(tool_handlers={}, tool_schemas=[])
        path = Path(session.socket_path)
        assert str(path).startswith(tempfile.gettempdir())

    def test_each_session_gets_unique_path(self) -> None:
        """Each IPCSession instance gets a unique socket path."""
        s1 = IPCSession(tool_handlers={}, tool_schemas=[])
        s2 = IPCSession(tool_handlers={}, tool_schemas=[])
        assert s1.socket_path != s2.socket_path


class TestIPCSessionSchemaFile:
    """IPCSession schema file creation."""

    @pytest.mark.asyncio
    async def test_schema_file_contains_correct_json(self) -> None:
        """Schema file contains JSON array of ToolSchema dicts."""
        schemas: list[ToolSchema] = [
            {
                "name": "add",
                "description": "Add numbers",
                "input_schema": {"type": "object"},
            },
            {
                "name": "sub",
                "description": "Subtract",
                "input_schema": {"type": "object"},
            },
        ]

        async def dummy(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"add": dummy, "sub": dummy},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            content = Path(session.schema_path).read_text(encoding="utf-8")
            loaded = json.loads(content)
            assert len(loaded) == 2
            assert loaded[0]["name"] == "add"
            assert loaded[1]["name"] == "sub"
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_schema_file_has_correct_permissions(self) -> None:
        """Schema file is created with 0o600 permissions."""
        schemas: list[ToolSchema] = [
            {"name": "t1", "description": "d1", "input_schema": {}},
        ]

        async def dummy(args: dict[str, object]) -> dict[str, object]:
            return {"content": [{"type": "text", "text": "ok"}]}

        session = IPCSession(
            tool_handlers={"t1": dummy},
            tool_schemas=schemas,
        )

        await session.start()
        try:
            mode = os.stat(session.schema_path).st_mode & 0o777
            assert mode == SOCKET_PERMISSIONS
        finally:
            await session.stop()

    def test_schema_path_has_correct_prefix(self) -> None:
        """Schema path filename starts with the expected prefix."""
        session = IPCSession(tool_handlers={}, tool_schemas=[])
        path = Path(session.schema_path)
        assert path.name.startswith(SCHEMA_FILE_PREFIX)
