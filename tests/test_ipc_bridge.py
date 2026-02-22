"""Tests for IPC bridge process.

Tests cover:
- Schema file loading (JSON → list[ToolSchema])
- MCP tools/list response from local schema
- MCP tools/call relay via IPC
- IPC connection failure → MCP error response
- Tool execution error propagation
"""

import asyncio
import json
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudecode_model.exceptions import IPCConnectionError, IPCError
from claudecode_model.ipc.protocol import (
    IPCErrorResponse,
    IPCResponse,
    ToolSchema,
)


# ── Schema file loading ──────────────────────────────────────────────────


class TestLoadSchemas:
    """Test schema file loading (JSON → list[ToolSchema])."""

    def test_load_schemas_from_valid_file(self, tmp_path: Path) -> None:
        """Load a JSON file containing tool schemas."""
        from claudecode_model.ipc.bridge import load_schemas

        schemas: list[ToolSchema] = [
            {
                "name": "calculator",
                "description": "Perform calculations",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        ]
        schema_file = tmp_path / "schemas.json"
        schema_file.write_text(json.dumps(schemas))

        result = load_schemas(schema_file)

        assert len(result) == 1
        assert result[0]["name"] == "calculator"
        assert result[0]["description"] == "Perform calculations"
        assert result[0]["input_schema"]["type"] == "object"

    def test_load_schemas_multiple_tools(self, tmp_path: Path) -> None:
        """Load multiple tool schemas from a JSON array."""
        from claudecode_model.ipc.bridge import load_schemas

        schemas: list[ToolSchema] = [
            {
                "name": "tool_a",
                "description": "First tool",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "tool_b",
                "description": "Second tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
            },
        ]
        schema_file = tmp_path / "schemas.json"
        schema_file.write_text(json.dumps(schemas))

        result = load_schemas(schema_file)

        assert len(result) == 2
        assert result[0]["name"] == "tool_a"
        assert result[1]["name"] == "tool_b"

    def test_load_schemas_empty_array(self, tmp_path: Path) -> None:
        """Load an empty array returns empty list."""
        from claudecode_model.ipc.bridge import load_schemas

        schema_file = tmp_path / "schemas.json"
        schema_file.write_text("[]")

        result = load_schemas(schema_file)

        assert result == []

    def test_load_schemas_file_not_found(self) -> None:
        """Raise error when schema file does not exist."""
        from claudecode_model.ipc.bridge import load_schemas

        with pytest.raises(FileNotFoundError):
            load_schemas(Path("/nonexistent/schemas.json"))

    def test_load_schemas_invalid_json(self, tmp_path: Path) -> None:
        """Raise error when file contains invalid JSON."""
        from claudecode_model.ipc.bridge import load_schemas

        schema_file = tmp_path / "schemas.json"
        schema_file.write_text("not valid json")

        with pytest.raises(json.JSONDecodeError):
            load_schemas(schema_file)


# ── MCP tools/list response ──────────────────────────────────────────────


class TestToolsListHandler:
    """Test MCP tools/list handler returns schemas as MCP Tool format."""

    def test_schemas_to_mcp_tools(self) -> None:
        """Convert ToolSchema list to MCP Tool objects."""
        from claudecode_model.ipc.bridge import schemas_to_mcp_tools

        schemas: list[ToolSchema] = [
            {
                "name": "calculator",
                "description": "Perform calculations",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        ]

        tools = schemas_to_mcp_tools(schemas)

        assert len(tools) == 1
        assert tools[0].name == "calculator"
        assert tools[0].description == "Perform calculations"
        assert tools[0].inputSchema == schemas[0]["input_schema"]

    def test_schemas_to_mcp_tools_multiple(self) -> None:
        """Convert multiple schemas to MCP Tool objects."""
        from claudecode_model.ipc.bridge import schemas_to_mcp_tools

        schemas: list[ToolSchema] = [
            {
                "name": "tool_a",
                "description": "First",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "tool_b",
                "description": "Second",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

        tools = schemas_to_mcp_tools(schemas)

        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"

    def test_schemas_to_mcp_tools_empty(self) -> None:
        """Convert empty schemas list returns empty list."""
        from claudecode_model.ipc.bridge import schemas_to_mcp_tools

        tools = schemas_to_mcp_tools([])
        assert tools == []


# ── IPC Client ────────────────────────────────────────────────────────────


class TestIPCClient:
    """Test IPC client with lazy connect and call_tool handling."""

    async def test_call_tool_sends_request_and_receives_response(self) -> None:
        """call_tool sends IPCRequest and returns parsed IPCResponse result."""
        from claudecode_model.ipc.bridge import IPCClient

        # Prepare mock response data
        response: IPCResponse = {
            "result": {
                "content": [{"type": "text", "text": "42"}],
            }
        }
        response_payload = json.dumps(response).encode("utf-8")
        response_frame = struct.pack("!I", len(response_payload)) + response_payload

        # Create mock reader/writer
        mock_reader = asyncio.StreamReader()
        mock_reader.feed_data(response_frame)
        mock_reader.feed_eof()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        written_data = bytearray()
        mock_writer.write = MagicMock(side_effect=lambda d: written_data.extend(d))
        mock_writer.drain = AsyncMock()

        client = IPCClient("/tmp/test.sock")
        # Inject mock connection
        client._reader = mock_reader
        client._writer = mock_writer
        client._connected = True

        result = await client.call_tool("calculator", {"expression": "6*7"})

        assert result == response["result"]

    async def test_call_tool_lazy_connects(self) -> None:
        """First call_tool triggers connection to socket."""
        from claudecode_model.ipc.bridge import IPCClient

        response: IPCResponse = {
            "result": {
                "content": [{"type": "text", "text": "ok"}],
            }
        }
        response_payload = json.dumps(response).encode("utf-8")
        response_frame = struct.pack("!I", len(response_payload)) + response_payload

        mock_reader = asyncio.StreamReader()
        mock_reader.feed_data(response_frame)
        mock_reader.feed_eof()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        client = IPCClient("/tmp/test.sock")

        assert not client._connected

        with patch(
            "asyncio.open_unix_connection",
            return_value=(mock_reader, mock_writer),
        ) as mock_connect:
            await client.call_tool("test_tool", {})

        mock_connect.assert_called_once_with("/tmp/test.sock")
        assert client._connected

    async def test_call_tool_reuses_connection(self) -> None:
        """Subsequent call_tool reuses the existing connection."""
        from claudecode_model.ipc.bridge import IPCClient

        def make_response_frame() -> bytes:
            response: IPCResponse = {
                "result": {
                    "content": [{"type": "text", "text": "ok"}],
                }
            }
            payload = json.dumps(response).encode("utf-8")
            return struct.pack("!I", len(payload)) + payload

        # Feed two responses
        mock_reader = asyncio.StreamReader()
        mock_reader.feed_data(make_response_frame())
        mock_reader.feed_data(make_response_frame())
        mock_reader.feed_eof()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        client = IPCClient("/tmp/test.sock")

        with patch(
            "asyncio.open_unix_connection",
            return_value=(mock_reader, mock_writer),
        ) as mock_connect:
            await client.call_tool("tool_a", {})
            await client.call_tool("tool_b", {})

        # Only one connection should be established
        mock_connect.assert_called_once()

    async def test_call_tool_connection_failure_raises_error(self) -> None:
        """Raise IPCConnectionError when socket connection fails."""
        from claudecode_model.ipc.bridge import IPCClient

        client = IPCClient("/tmp/nonexistent.sock")

        with patch(
            "asyncio.open_unix_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            with pytest.raises(IPCConnectionError):
                await client.call_tool("test_tool", {})

    async def test_call_tool_propagates_error_response(self) -> None:
        """Propagate IPCErrorResponse as IPCError."""
        from claudecode_model.ipc.bridge import IPCClient

        error_response: IPCErrorResponse = {
            "error": {
                "message": "Tool 'unknown' not found",
                "type": "ToolNotFoundError",
            }
        }
        payload = json.dumps(error_response).encode("utf-8")
        frame = struct.pack("!I", len(payload)) + payload

        mock_reader = asyncio.StreamReader()
        mock_reader.feed_data(frame)
        mock_reader.feed_eof()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        client = IPCClient("/tmp/test.sock")
        client._reader = mock_reader
        client._writer = mock_writer
        client._connected = True

        with pytest.raises(IPCError, match="Tool 'unknown' not found"):
            await client.call_tool("unknown", {})

    async def test_call_tool_propagates_tool_execution_error(self) -> None:
        """Propagate tool execution error from parent process."""
        from claudecode_model.ipc.bridge import IPCClient

        error_response: IPCErrorResponse = {
            "error": {
                "message": "Division by zero",
                "type": "ZeroDivisionError",
            }
        }
        payload = json.dumps(error_response).encode("utf-8")
        frame = struct.pack("!I", len(payload)) + payload

        mock_reader = asyncio.StreamReader()
        mock_reader.feed_data(frame)
        mock_reader.feed_eof()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        client = IPCClient("/tmp/test.sock")
        client._reader = mock_reader
        client._writer = mock_writer
        client._connected = True

        with pytest.raises(IPCError, match="Division by zero"):
            await client.call_tool("calculator", {"expression": "1/0"})
