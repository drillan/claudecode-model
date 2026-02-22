"""IPC bridge process: MCP stdio ↔ IPC relay.

This module implements the bridge process that the CLI starts as a subprocess.
It acts as a standard MCP stdio server (JSON-RPC 2.0 over stdin/stdout) and
relays ``tools/call`` requests to the parent process via a Unix domain socket
using the length-prefixed IPC protocol.

``tools/list`` requests are answered locally from a schema file loaded at
startup, so no IPC connection is needed for tool discovery.

Usage::

    python -m claudecode_model.ipc.bridge <socket_path> <schema_path>
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from claudecode_model.exceptions import IPCConnectionError, IPCError
from claudecode_model.ipc.protocol import (
    IPCRequest,
    ToolResult,
    ToolSchema,
    receive_message,
    send_message,
)

logger = logging.getLogger(__name__)


# ── Schema loading ────────────────────────────────────────────────────────


def load_schemas(schema_path: Path) -> list[ToolSchema]:
    """Load tool schemas from a JSON file.

    Args:
        schema_path: Path to the JSON file containing a ``list[ToolSchema]`` array.

    Returns:
        List of tool schemas.

    Raises:
        FileNotFoundError: If *schema_path* does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    text = schema_path.read_text(encoding="utf-8")
    schemas: list[ToolSchema] = json.loads(text)
    logger.debug("Loaded %d tool schemas from %s", len(schemas), schema_path)
    return schemas


# ── Schema → MCP Tool conversion ─────────────────────────────────────────


def schemas_to_mcp_tools(schemas: list[ToolSchema]) -> list[Tool]:
    """Convert tool schemas to MCP :class:`Tool` objects.

    Args:
        schemas: List of tool schemas loaded from the schema file.

    Returns:
        List of MCP Tool objects suitable for ``tools/list`` responses.
    """
    return [
        Tool(
            name=schema["name"],
            description=schema["description"],
            inputSchema=schema["input_schema"],
        )
        for schema in schemas
    ]


# ── IPC Client ────────────────────────────────────────────────────────────


class IPCClient:
    """Client for communicating with the parent process IPC server.

    Uses lazy connection: the Unix socket connection is established on the first
    ``call_tool`` invocation and reused for subsequent calls.

    Args:
        socket_path: Path to the Unix domain socket.
    """

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected: bool = False

    async def _connect(self) -> None:
        """Establish connection to the IPC server.

        Raises:
            IPCConnectionError: If the connection cannot be established.
        """
        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                self._socket_path
            )
            self._connected = True
            logger.debug("Connected to IPC server at %s", self._socket_path)
        except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
            raise IPCConnectionError(
                f"Cannot connect to IPC server at {self._socket_path}: {exc}"
            ) from exc

    async def call_tool(self, name: str, arguments: dict[str, object]) -> ToolResult:
        """Send a ``call_tool`` request and return the result.

        Lazily connects to the IPC server on first invocation.

        Args:
            name: Tool name to invoke.
            arguments: Tool arguments.

        Returns:
            The :class:`ToolResult` from the parent process.

        Raises:
            IPCConnectionError: If the IPC server is unreachable.
            IPCError: If the parent returns an error response or
                communication fails.
        """
        if not self._connected:
            await self._connect()

        assert self._reader is not None  # noqa: S101
        assert self._writer is not None  # noqa: S101

        request: IPCRequest = {
            "method": "call_tool",
            "params": {"name": name, "arguments": arguments},
        }

        await send_message(self._writer, request)
        raw_response = await receive_message(self._reader)

        # Check for error response
        if "error" in raw_response:
            error_payload = raw_response["error"]
            assert isinstance(error_payload, dict)  # noqa: S101
            error_message = str(error_payload.get("message", "Unknown IPC error"))
            error_type = str(error_payload.get("type", "IPCError"))
            raise IPCError(f"{error_message} (type: {error_type})")

        # Extract result
        if "result" not in raw_response:
            raise IPCError(
                "Invalid IPC response: missing both 'result' and 'error' fields"
            )

        result = raw_response["result"]
        assert isinstance(result, dict)  # noqa: S101
        return result  # type: ignore[return-value]

    async def close(self) -> None:
        """Close the IPC connection."""
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
            self._connected = False
            self._reader = None
            self._writer = None
            logger.debug("IPC connection closed")


# ── MCP Server assembly ──────────────────────────────────────────────────


def create_bridge_server(
    schemas: list[ToolSchema],
    ipc_client: IPCClient,
) -> Server:
    """Create an MCP server wired to the IPC client.

    Args:
        schemas: Tool schemas loaded from the schema file.
        ipc_client: IPC client for relaying ``call_tool`` requests.

    Returns:
        Configured :class:`mcp.server.Server` ready to serve via stdio.
    """
    mcp_tools = schemas_to_mcp_tools(schemas)
    server = Server("claudecode-bridge")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return mcp_tools

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, object] | None
    ) -> list[TextContent]:
        result = await ipc_client.call_tool(name, arguments or {})
        content_list = result.get("content", [])
        assert isinstance(content_list, list)  # noqa: S101
        return [
            TextContent(type="text", text=str(item.get("text", "")))
            for item in content_list
            if isinstance(item, dict)
        ]

    return server


# ── Entry point ───────────────────────────────────────────────────────────


async def _run_bridge(socket_path: str, schema_path: str) -> None:
    """Start the bridge process.

    Args:
        socket_path: Path to the parent process IPC Unix socket.
        schema_path: Path to the tool schema JSON file.
    """
    schemas = load_schemas(Path(schema_path))
    ipc_client = IPCClient(socket_path)
    server = create_bridge_server(schemas, ipc_client)

    logger.info(
        "Bridge starting: socket=%s, schema=%s, tools=%d",
        socket_path,
        schema_path,
        len(schemas),
    )

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await ipc_client.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:  # noqa: PLR2004
        print(
            f"Usage: {sys.executable} -m claudecode_model.ipc.bridge "
            "<socket_path> <schema_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(_run_bridge(sys.argv[1], sys.argv[2]))
