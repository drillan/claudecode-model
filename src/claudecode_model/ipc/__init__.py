"""IPC bridge package for Claude Code CLI tool communication.

This package provides the IPC (Inter-Process Communication) bridge mechanism
that enables pydantic-ai tools registered via ``set_agent_toolsets()`` to be
invoked through the Claude Code CLI, regardless of CLI version support for
``type: "sdk"`` MCP servers.

Architecture:
    Parent Process (IPCServer) <-- Unix domain socket --> Bridge Process (MCP stdio)
"""

from typing import Literal

type TransportType = Literal["auto", "stdio", "sdk"]
"""Transport mode for tool communication.

- ``"auto"``: Currently equivalent to ``"stdio"``. Will switch to ``"sdk"``
  when CLI natively supports it.
- ``"stdio"``: IPC bridge mode via Unix domain socket.
- ``"sdk"``: Legacy SDK mode (``McpSdkServerConfig``).
"""

DEFAULT_TRANSPORT: TransportType = "auto"
"""Default transport mode."""

__all__ = [
    "TransportType",
    "DEFAULT_TRANSPORT",
]
