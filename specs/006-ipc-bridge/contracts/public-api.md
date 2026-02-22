# Contract: Public API Changes

**Feature Branch**: `006-ipc-bridge`
**Date**: 2026-02-22
**Type**: Library Public API

## Modified API

### `set_agent_toolsets()`

**Module**: `claudecode_model.model.ClaudeCodeModel`

#### Before (existing)

```python
def set_agent_toolsets(
    self,
    toolsets: Sequence[PydanticAITool] | AgentToolset | None,
    *,
    server_name: str = MCP_SERVER_NAME,
) -> None: ...
```

#### After (with transport parameter)

```python
def set_agent_toolsets(
    self,
    toolsets: Sequence[PydanticAITool] | AgentToolset | None,
    *,
    server_name: str = MCP_SERVER_NAME,
    transport: TransportType = DEFAULT_TRANSPORT,
) -> None: ...
```

**Changes**:
- Added `transport` keyword argument (backward-compatible, has default value)
- No breaking changes to existing callers (FR-011)

**Internal type change** (not part of public API):
- `self._mcp_servers` type annotation widens from `dict[str, McpSdkServerConfig]` to `dict[str, McpSdkServerConfig | McpStdioServerConfig]`
- `get_mcp_servers()` return type widens accordingly
- `ClaudeAgentOptions.mcp_servers` accepts `dict[str, McpSdkServerConfig | McpStdioServerConfig]` (verified compatible)

**Behavior by transport value**:

| Value | Behavior |
|-------|----------|
| `"auto"` | Currently equivalent to `"stdio"`. Default value. |
| `"stdio"` | Creates `McpStdioServerConfig` pointing to bridge process. IPC server managed per-request. |
| `"sdk"` | Existing behavior. Creates `McpSdkServerConfig`. |

---

## New Public Types

### `TransportType`

**Module**: `claudecode_model.ipc`

```python
type TransportType = Literal["auto", "stdio", "sdk"]
```

**Export**: Via `claudecode_model.__init__`

---

## New Public Constants

### `DEFAULT_TRANSPORT`

**Module**: `claudecode_model.ipc`

```python
DEFAULT_TRANSPORT: TransportType = "auto"
```

**Export**: Via `claudecode_model.__init__`

---

## New Exception Classes

**Module**: `claudecode_model.exceptions`

```python
class IPCError(ClaudeCodeError):
    """Base exception for IPC communication errors."""
    pass

class IPCConnectionError(IPCError):
    """Bridge process failed to connect to IPC server."""
    pass

class IPCMessageSizeError(IPCError):
    """IPC message exceeds maximum allowed size."""
    pass

class IPCToolExecutionError(IPCError):
    """Tool function execution failed during IPC call."""
    pass

class BridgeStartupError(IPCError):
    """Bridge process failed to start or initialize."""
    pass
```

**Export**: All via `claudecode_model.__init__`

---

## Behavioral Contract

### IPC Lifecycle

For `transport="stdio"` or `transport="auto"`:

1. **`set_agent_toolsets()` call**: Prepares IPC configuration (socket path, schema file, `McpStdioServerConfig`). Does NOT start the IPC server.

2. **`request()` / `stream_messages()` / `request_with_metadata()` call**:
   - Before SDK query: Starts IPC server (async)
   - During SDK query: Bridge process connects to IPC server
   - After SDK query: Stops IPC server, deletes socket file and schema file (guaranteed even on exception)

3. **`_process_function_tools()` call**: Regenerates IPC configuration with filtered tools. Next request will use the updated configuration.

### Error Propagation

- Tool execution errors are propagated as `IPCToolExecutionError` (never silently ignored)
- IPC communication errors are propagated as `IPCError` or subclasses
- Bridge process startup failures are propagated as `BridgeStartupError`
