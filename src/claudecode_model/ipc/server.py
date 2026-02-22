"""IPC server: Unix domain socket server for tool execution (parent process side).

This module implements the IPC server that runs in the parent process, accepting
``call_tool`` requests from the bridge process via a Unix domain socket and
dispatching them to registered tool handlers.

Architecture::

    Bridge Process  ── call_tool request ──>  IPCServer  ── dispatch ──>  ToolHandler
                    <── IPCResponse/Error ──
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from claudecode_model.ipc.protocol import (
    SCHEMA_FILE_PREFIX,
    SOCKET_FILE_PREFIX,
    SOCKET_FILE_SUFFIX,
    SOCKET_PERMISSIONS,
    IPCErrorResponse,
    IPCResponse,
    ToolSchema,
    receive_message,
    send_message,
)

logger = logging.getLogger(__name__)

# Type alias matching create_tool_wrapper() signature
ToolHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


# ── IPCServer ────────────────────────────────────────────────────────────


class IPCServer:
    """Asyncio Unix domain socket server for IPC tool execution.

    Listens on a Unix socket and dispatches incoming ``call_tool`` requests
    to the appropriate registered handler.

    Args:
        socket_path: Path for the Unix domain socket file.
        tool_handlers: Mapping of tool names to async handler functions.
    """

    def __init__(
        self,
        socket_path: str,
        tool_handlers: dict[str, ToolHandler],
    ) -> None:
        self._socket_path = socket_path
        self._tool_handlers = tool_handlers
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start the IPC server and bind to the Unix socket.

        After this method returns, the server is ready to accept connections.
        """
        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=self._socket_path,
        )
        # Set socket permissions to owner-only (FR-009)
        os.chmod(self._socket_path, SOCKET_PERMISSIONS)
        logger.debug("IPCServer started on %s", self._socket_path)

    async def stop(self) -> None:
        """Stop the IPC server and remove the socket file."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.debug("IPCServer stopped")

        # Remove socket file
        socket = Path(self._socket_path)
        if socket.exists():
            socket.unlink()
            logger.debug("Removed socket file %s", self._socket_path)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a persistent client connection.

        Reads IPC requests in a loop, dispatching each to the appropriate
        handler and sending the response back.  The loop terminates when
        the client disconnects (EOF / connection reset).
        """
        try:
            while True:
                try:
                    raw_request = await receive_message(reader)
                except (asyncio.IncompleteReadError, ConnectionError):
                    break  # Client disconnected
                try:
                    response = await self._dispatch(raw_request)
                    await send_message(writer, response)
                except (ConnectionError, OSError):
                    break  # Connection lost during response
        except Exception:
            logger.error("Error handling IPC connection", exc_info=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _dispatch(
        self, raw_request: dict[str, object]
    ) -> IPCResponse | IPCErrorResponse:
        """Dispatch an IPC request to the appropriate handler.

        Args:
            raw_request: The deserialized IPC request message.

        Returns:
            An IPCResponse on success or IPCErrorResponse on failure.
        """
        method = raw_request.get("method")
        if method != "call_tool":
            return _error_response(
                f"Unknown method: {method}",
                "ValueError",
            )

        params = raw_request.get("params")
        if not isinstance(params, dict):
            return _error_response(
                "Invalid params: expected dict",
                "ValueError",
            )

        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            return _error_response(
                "Invalid tool name: expected string",
                "ValueError",
            )

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error_response(
                "Invalid arguments: expected dict",
                "ValueError",
            )

        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return _error_response(
                f"Unknown tool: {tool_name}",
                "ToolNotFoundError",
            )

        try:
            result = await handler(arguments)
            response: IPCResponse = {"result": result}  # type: ignore[typeddict-item]
            return response
        except Exception as exc:
            logger.error(
                "Tool '%s' execution failed: %s",
                tool_name,
                exc,
                exc_info=True,
            )
            return _error_response(str(exc), type(exc).__name__)


def _error_response(message: str, error_type: str) -> IPCErrorResponse:
    """Create an IPCErrorResponse."""
    return {"error": {"message": message, "type": error_type}}


# ── IPCSession ───────────────────────────────────────────────────────────


class IPCSession:
    """Manages an IPC session lifecycle: paths, schema file, and server.

    An IPCSession encapsulates the creation of socket/schema paths with UUID
    for uniqueness, writing the tool schema file, and starting/stopping the
    underlying ``IPCServer``.

    Args:
        tool_handlers: Mapping of tool names to async handler functions.
        tool_schemas: List of tool schemas to write to the schema file.
    """

    def __init__(
        self,
        tool_handlers: dict[str, ToolHandler],
        tool_schemas: list[ToolSchema],
    ) -> None:
        session_id = uuid.uuid4().hex
        tmp_dir = tempfile.gettempdir()

        self._socket_path = str(
            Path(tmp_dir) / f"{SOCKET_FILE_PREFIX}{session_id}{SOCKET_FILE_SUFFIX}"
        )
        self._schema_path = str(
            Path(tmp_dir) / f"{SCHEMA_FILE_PREFIX}{session_id}.json"
        )
        self._tool_handlers = tool_handlers
        self._tool_schemas = tool_schemas
        self._server: IPCServer | None = None
        self._started = False

    @property
    def socket_path(self) -> str:
        """Path to the Unix domain socket file."""
        return self._socket_path

    @property
    def schema_path(self) -> str:
        """Path to the tool schema JSON file."""
        return self._schema_path

    async def start(self) -> None:
        """Start the IPC session: clean stale sockets, write schema, start server.

        Scans the temp directory for stale socket files from previous sessions
        and removes them before starting this session's server.
        """
        if self._started:
            return

        # Clean up stale socket files from previous crashes (FR-010)
        self._cleanup_stale_sockets()

        # Write schema file with restricted permissions
        self._write_schema_file()

        # Start IPC server
        self._server = IPCServer(self._socket_path, self._tool_handlers)
        await self._server.start()
        self._started = True

        logger.info(
            "IPCSession started: socket=%s, schema=%s, tools=%d",
            self._socket_path,
            self._schema_path,
            len(self._tool_schemas),
        )

    def _cleanup_stale_sockets(self) -> None:
        """Remove stale socket files from previous sessions.

        Scans the temp directory for files matching the ``claudecode_ipc_*.sock``
        pattern and removes any that do not belong to this session.
        """
        tmp_dir = Path(tempfile.gettempdir())
        pattern = f"{SOCKET_FILE_PREFIX}*{SOCKET_FILE_SUFFIX}"
        own_socket = Path(self._socket_path).name

        for stale_path in tmp_dir.glob(pattern):
            if stale_path.name == own_socket:
                continue
            try:
                stale_path.unlink()
                logger.info("Removed stale socket file: %s", stale_path)
            except OSError:
                logger.warning(
                    "Failed to remove stale socket file: %s",
                    stale_path,
                    exc_info=True,
                )

    async def stop(self) -> None:
        """Stop the IPC session: stop server and clean up files.

        This method is idempotent — calling it multiple times is safe.
        """
        if self._server is not None:
            await self._server.stop()
            self._server = None

        # Clean up schema file
        schema = Path(self._schema_path)
        if schema.exists():
            schema.unlink()
            logger.debug("Removed schema file %s", self._schema_path)

        self._started = False

    def _write_schema_file(self) -> None:
        """Write tool schemas to a JSON file with 0o600 permissions."""
        schema_path = Path(self._schema_path)

        # Write with restricted permissions using os.open + os.fdopen
        fd = os.open(
            str(schema_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            SOCKET_PERMISSIONS,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._tool_schemas, f)
        except Exception:
            # fd is closed by os.fdopen even on error
            raise

        logger.debug(
            "Schema file written: %s (%d tools)",
            self._schema_path,
            len(self._tool_schemas),
        )
