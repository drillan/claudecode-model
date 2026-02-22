"""IPC protocol: message types, constants, and length-prefixed framing.

This module defines the wire protocol between the parent process (IPC server)
and the bridge process (MCP stdio server). Messages are JSON-encoded and
transmitted over a Unix domain socket using length-prefixed framing.

Wire format::

    [4 bytes: payload length (big-endian uint32)][N bytes: UTF-8 JSON payload]
"""

import asyncio
import json
import struct
from collections.abc import Mapping
from typing import TypedDict

from claudecode_model.exceptions import IPCError, IPCMessageSizeError

# ── Constants ──────────────────────────────────────────────────────────────

MAX_MESSAGE_SIZE: int = 10_485_760
"""Maximum IPC message payload size in bytes (10 MB)."""

LENGTH_PREFIX_SIZE: int = 4
"""Byte count for the message length prefix (big-endian uint32)."""

SOCKET_PERMISSIONS: int = 0o600
"""Unix permission bits for socket files (owner read/write only)."""

SOCKET_FILE_PREFIX: str = "claudecode_ipc_"
"""Prefix for socket file names in the temp directory."""

SOCKET_FILE_SUFFIX: str = ".sock"
"""Suffix for socket file names."""

SCHEMA_FILE_PREFIX: str = "claudecode_ipc_schema_"
"""Prefix for tool schema temporary file names."""


# ── Message TypedDicts ─────────────────────────────────────────────────────


class CallToolParams(TypedDict):
    """Parameters for a ``call_tool`` request."""

    name: str
    arguments: dict[str, object]


class IPCRequest(TypedDict):
    """Request message from bridge to parent (call_tool only)."""

    method: str
    params: CallToolParams


class ToolResultContent(TypedDict):
    """Single content block in a tool result (MCP TextContent)."""

    type: str
    text: str


class _ToolResultRequired(TypedDict):
    content: list[ToolResultContent]


class ToolResult(_ToolResultRequired, total=False):
    """Tool execution result (MCP CallToolResult compatible).

    ``content`` is required; ``isError`` is optional (defaults to ``False``).
    """

    isError: bool


class IPCResponse(TypedDict):
    """Success response from parent to bridge."""

    result: ToolResult


class IPCErrorPayload(TypedDict):
    """Error information on the wire (distinct from Python exception classes)."""

    message: str
    type: str


class IPCErrorResponse(TypedDict):
    """Error response from parent to bridge."""

    error: IPCErrorPayload


class ToolSchema(TypedDict):
    """Tool schema passed to bridge process via temp file."""

    name: str
    description: str
    input_schema: dict[str, object]


# ── Length-prefixed framing ────────────────────────────────────────────────


async def send_message(
    writer: asyncio.StreamWriter,
    message: Mapping[str, object],
) -> None:
    """Serialize *message* to JSON and send with a length prefix.

    Args:
        writer: An asyncio stream writer (e.g. from a Unix socket connection).
        message: A JSON-serializable dictionary.

    Raises:
        IPCMessageSizeError: If the encoded payload exceeds ``MAX_MESSAGE_SIZE``.
    """
    payload = json.dumps(message).encode("utf-8")
    if len(payload) > MAX_MESSAGE_SIZE:
        raise IPCMessageSizeError(
            f"Message size {len(payload)} bytes exceeds "
            f"MAX_MESSAGE_SIZE ({MAX_MESSAGE_SIZE} bytes)"
        )
    prefix = struct.pack("!I", len(payload))
    writer.write(prefix + payload)
    await writer.drain()


async def receive_message(
    reader: asyncio.StreamReader,
) -> dict[str, object]:
    """Read a length-prefixed message and deserialize from JSON.

    Args:
        reader: An asyncio stream reader (e.g. from a Unix socket connection).

    Returns:
        The deserialized JSON object as a ``dict``.

    Raises:
        IPCError: If the stream ends prematurely or contains invalid JSON.
        IPCMessageSizeError: If the declared payload length exceeds
            ``MAX_MESSAGE_SIZE``.
    """
    try:
        prefix = await reader.readexactly(LENGTH_PREFIX_SIZE)
    except asyncio.IncompleteReadError as exc:
        raise IPCError(
            f"Incomplete length prefix: expected {LENGTH_PREFIX_SIZE} bytes, "
            f"got {len(exc.partial)}"
        ) from exc

    (payload_length,) = struct.unpack("!I", prefix)
    if payload_length > MAX_MESSAGE_SIZE:
        raise IPCMessageSizeError(
            f"Declared message size {payload_length} bytes exceeds "
            f"MAX_MESSAGE_SIZE ({MAX_MESSAGE_SIZE} bytes)"
        )

    try:
        payload = await reader.readexactly(payload_length)
    except asyncio.IncompleteReadError as exc:
        raise IPCError(
            f"Incomplete payload: expected {payload_length} bytes, "
            f"got {len(exc.partial)}"
        ) from exc

    try:
        data: dict[str, object] = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IPCError(f"Invalid JSON in IPC message: {exc}") from exc

    return data
