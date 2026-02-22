"""Tests for IPC protocol module.

Tests cover:
- Message TypedDict construction (IPCRequest, IPCResponse, IPCErrorResponse)
- ToolSchema construction and JSON serialization round-trip
- Length-prefix framing (send/receive round-trip)
- MAX_MESSAGE_SIZE exceeded error
- Empty message handling
- Invalid JSON handling
"""

import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from claudecode_model.exceptions import IPCError, IPCMessageSizeError
from claudecode_model.ipc.protocol import (
    LENGTH_PREFIX_SIZE,
    MAX_MESSAGE_SIZE,
    SCHEMA_FILE_PREFIX,
    SOCKET_FILE_PREFIX,
    SOCKET_FILE_SUFFIX,
    SOCKET_PERMISSIONS,
    CallToolParams,
    IPCErrorPayload,
    IPCErrorResponse,
    IPCRequest,
    IPCResponse,
    ToolResult,
    ToolResultContent,
    ToolSchema,
    receive_message,
    send_message,
)


class TestProtocolConstants:
    """Test protocol constants are correctly defined."""

    def test_max_message_size(self) -> None:
        assert MAX_MESSAGE_SIZE == 10_485_760

    def test_length_prefix_size(self) -> None:
        assert LENGTH_PREFIX_SIZE == 4

    def test_socket_permissions(self) -> None:
        assert SOCKET_PERMISSIONS == 0o600

    def test_socket_file_prefix(self) -> None:
        assert SOCKET_FILE_PREFIX == "claudecode_ipc_"

    def test_socket_file_suffix(self) -> None:
        assert SOCKET_FILE_SUFFIX == ".sock"

    def test_schema_file_prefix(self) -> None:
        assert SCHEMA_FILE_PREFIX == "claudecode_ipc_schema_"


class TestMessageTypedDicts:
    """Test TypedDict construction for IPC messages."""

    def test_ipc_request_construction(self) -> None:
        params: CallToolParams = {"name": "my_tool", "arguments": {"key": "value"}}
        request: IPCRequest = {"method": "call_tool", "params": params}

        assert request["method"] == "call_tool"
        assert request["params"]["name"] == "my_tool"
        assert request["params"]["arguments"] == {"key": "value"}

    def test_ipc_response_construction(self) -> None:
        content: ToolResultContent = {"type": "text", "text": "result text"}
        result: ToolResult = {"content": [content]}
        response: IPCResponse = {"result": result}

        assert response["result"]["content"][0]["type"] == "text"
        assert response["result"]["content"][0]["text"] == "result text"

    def test_ipc_response_with_is_error(self) -> None:
        content: ToolResultContent = {"type": "text", "text": "error info"}
        result: ToolResult = {"content": [content], "isError": True}
        response: IPCResponse = {"result": result}

        assert response["result"]["isError"] is True

    def test_ipc_error_response_construction(self) -> None:
        payload: IPCErrorPayload = {
            "message": "Tool not found: unknown_tool",
            "type": "ToolNotFoundError",
        }
        error_response: IPCErrorResponse = {"error": payload}

        assert error_response["error"]["message"] == "Tool not found: unknown_tool"
        assert error_response["error"]["type"] == "ToolNotFoundError"

    def test_ipc_request_json_round_trip(self) -> None:
        params: CallToolParams = {
            "name": "calculator",
            "arguments": {"expression": "2+2"},
        }
        request: IPCRequest = {"method": "call_tool", "params": params}

        serialized = json.dumps(request)
        deserialized = json.loads(serialized)

        assert deserialized == request

    def test_ipc_response_json_round_trip(self) -> None:
        content: ToolResultContent = {"type": "text", "text": "4"}
        result: ToolResult = {"content": [content], "isError": False}
        response: IPCResponse = {"result": result}

        serialized = json.dumps(response)
        deserialized = json.loads(serialized)

        assert deserialized == response

    def test_ipc_error_response_json_round_trip(self) -> None:
        payload: IPCErrorPayload = {
            "message": "Division by zero",
            "type": "ZeroDivisionError",
        }
        error_response: IPCErrorResponse = {"error": payload}

        serialized = json.dumps(error_response)
        deserialized = json.loads(serialized)

        assert deserialized == error_response


class TestToolSchema:
    """Test ToolSchema construction and JSON serialization."""

    def test_tool_schema_construction(self) -> None:
        schema: ToolSchema = {
            "name": "calculator",
            "description": "Perform calculations",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
                "required": ["expression"],
            },
        }

        assert schema["name"] == "calculator"
        assert schema["description"] == "Perform calculations"
        assert schema["input_schema"]["type"] == "object"

    def test_tool_schema_list_json_round_trip(self) -> None:
        schemas: list[ToolSchema] = [
            {
                "name": "tool_a",
                "description": "First tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
            },
            {
                "name": "tool_b",
                "description": "Second tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"y": {"type": "string"}},
                },
            },
        ]

        serialized = json.dumps(schemas)
        deserialized = json.loads(serialized)

        assert len(deserialized) == 2
        assert deserialized[0]["name"] == "tool_a"
        assert deserialized[1]["name"] == "tool_b"
        assert deserialized == schemas

    def test_tool_schema_with_complex_input_schema(self) -> None:
        schema: ToolSchema = {
            "name": "complex_tool",
            "description": "A tool with nested schema",
            "input_schema": {
                "type": "object",
                "properties": {
                    "nested": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }

        serialized = json.dumps(schema)
        deserialized = json.loads(serialized)
        assert deserialized == schema


def _create_mock_writer() -> tuple[MagicMock, bytearray]:
    """Create a mock StreamWriter that captures written bytes."""
    buffer = bytearray()
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.write = MagicMock(side_effect=lambda data: buffer.extend(data))
    writer.drain = AsyncMock()
    return writer, buffer


def _create_reader_with_data(data: bytes) -> asyncio.StreamReader:
    """Create a StreamReader pre-filled with data."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class TestLengthPrefixFraming:
    """Test length-prefixed message framing (send/receive round-trip)."""

    async def test_send_receive_round_trip(self) -> None:
        message = {"method": "call_tool", "params": {"name": "test", "arguments": {}}}

        writer, buffer = _create_mock_writer()
        await send_message(writer, message)

        reader = _create_reader_with_data(bytes(buffer))
        received = await receive_message(reader)

        assert received == message

    async def test_send_message_format(self) -> None:
        message = {"key": "value"}

        writer, buffer = _create_mock_writer()
        await send_message(writer, message)

        payload = json.dumps(message).encode("utf-8")
        expected_prefix = struct.pack("!I", len(payload))

        assert bytes(buffer[:LENGTH_PREFIX_SIZE]) == expected_prefix
        assert bytes(buffer[LENGTH_PREFIX_SIZE:]) == payload

    async def test_receive_message_parses_json(self) -> None:
        message = {"result": {"content": [{"type": "text", "text": "hello"}]}}
        payload = json.dumps(message).encode("utf-8")
        prefix = struct.pack("!I", len(payload))

        reader = _create_reader_with_data(prefix + payload)
        received = await receive_message(reader)

        assert received == message

    async def test_send_receive_multiple_messages(self) -> None:
        messages: list[dict[str, object]] = [
            {"method": "call_tool", "params": {"name": "a", "arguments": {}}},
            {"result": {"content": [{"type": "text", "text": "ok"}]}},
        ]

        writer, buffer = _create_mock_writer()
        for msg in messages:
            await send_message(writer, msg)

        reader = _create_reader_with_data(bytes(buffer))
        received = []
        for _ in messages:
            received.append(await receive_message(reader))

        assert received == messages

    async def test_send_message_with_unicode(self) -> None:
        message = {"text": "日本語テスト 🚀"}

        writer, buffer = _create_mock_writer()
        await send_message(writer, message)

        reader = _create_reader_with_data(bytes(buffer))
        received = await receive_message(reader)

        assert received == message


class TestMaxMessageSizeValidation:
    """Test MAX_MESSAGE_SIZE exceeded error."""

    async def test_send_message_exceeding_max_size_raises_error(self) -> None:
        large_value = "x" * MAX_MESSAGE_SIZE
        message = {"data": large_value}

        writer, _ = _create_mock_writer()

        with pytest.raises(IPCMessageSizeError):
            await send_message(writer, message)

    async def test_receive_message_with_oversized_length_prefix_raises_error(
        self,
    ) -> None:
        oversized_length = MAX_MESSAGE_SIZE + 1
        prefix = struct.pack("!I", oversized_length)
        reader = _create_reader_with_data(prefix + b"x" * 10)

        with pytest.raises(IPCMessageSizeError):
            await receive_message(reader)

    async def test_message_at_exact_max_size_succeeds(self) -> None:
        # Create a message whose JSON payload is exactly MAX_MESSAGE_SIZE bytes
        # We need to calculate the overhead of JSON encoding
        base_message = {"d": ""}
        base_overhead = len(json.dumps(base_message).encode("utf-8")) - 0
        # Fill to exact limit
        fill_size = MAX_MESSAGE_SIZE - base_overhead
        message = {"d": "a" * fill_size}

        # Verify it's exactly at the limit
        payload = json.dumps(message).encode("utf-8")
        assert len(payload) == MAX_MESSAGE_SIZE

        writer, buffer = _create_mock_writer()
        await send_message(writer, message)

        reader = _create_reader_with_data(bytes(buffer))
        received = await receive_message(reader)
        assert received == message


class TestEmptyMessageHandling:
    """Test empty message handling."""

    async def test_receive_empty_stream_raises_error(self) -> None:
        reader = _create_reader_with_data(b"")

        with pytest.raises(IPCError):
            await receive_message(reader)

    async def test_receive_incomplete_length_prefix_raises_error(self) -> None:
        reader = _create_reader_with_data(b"\x00\x00")

        with pytest.raises(IPCError):
            await receive_message(reader)


class TestInvalidJsonHandling:
    """Test invalid JSON handling."""

    async def test_receive_invalid_json_raises_error(self) -> None:
        invalid_json = b"not valid json {{"
        prefix = struct.pack("!I", len(invalid_json))

        reader = _create_reader_with_data(prefix + invalid_json)

        with pytest.raises(IPCError):
            await receive_message(reader)

    async def test_receive_truncated_payload_raises_error(self) -> None:
        payload = json.dumps({"key": "value"}).encode("utf-8")
        prefix = struct.pack("!I", len(payload))
        # Send only half the payload
        truncated = prefix + payload[: len(payload) // 2]

        reader = _create_reader_with_data(truncated)

        with pytest.raises(IPCError):
            await receive_message(reader)
