# Contract: IPC Protocol

**Feature Branch**: `006-ipc-bridge`
**Date**: 2026-02-22
**Type**: Internal Protocol (Parent Process ↔ Bridge Process)

## Transport

- **Medium**: Unix domain socket
- **Framing**: Length-prefixed messages
  - 4 bytes: payload length (big-endian unsigned 32-bit integer)
  - N bytes: UTF-8 encoded JSON payload
- **Connection model**: Persistent connection (lazy connect on first `call_tool`)
- **Concurrency**: Strictly sequential (one request at a time per connection)
  - The bridge MUST wait for a response before sending the next request
  - Sending concurrent requests on the same connection is a protocol violation
- **Max message size**: 10,485,760 bytes (10 MB)

## Messages

### call_tool Request

**Direction**: Bridge → Parent

```json
{
    "method": "call_tool",
    "params": {
        "name": "<string: tool name>",
        "arguments": { "<string>": "<JsonValue>" }
    }
}
```

**Constraints**:
- `name` MUST match a registered tool name
- `arguments` MUST conform to the tool's input schema
- Serialized size MUST NOT exceed max message size

### call_tool Success Response

**Direction**: Parent → Bridge

```json
{
    "result": {
        "content": [
            { "type": "text", "text": "<string: result>" }
        ],
        "isError": false
    }
}
```

**Constraints**:
- `content` MUST contain at least one element
- `isError` defaults to `false` and MAY be omitted

### call_tool Error Response

**Direction**: Parent → Bridge

```json
{
    "error": {
        "message": "<string: error description>",
        "type": "<string: exception class name>"
    }
}
```

**Constraints**:
- `message` MUST provide actionable error information
- `type` MUST be the Python exception class name

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Bridge cannot connect to socket | Bridge returns MCP error to CLI |
| Message exceeds max size | Sender raises `IPCMessageSizeError` |
| Invalid JSON received | Receiver raises `IPCError` |
| Unknown method | Parent returns error response |
| Tool not found | Parent returns error response with `type: "ToolNotFoundError"` |
| Tool execution exception | Parent returns error response with exception details |
| Connection lost mid-request | Bridge returns MCP error to CLI |

## Schema File Format

**Path**: Passed as command-line argument to bridge process
**Format**: JSON array of tool schemas

```json
[
    {
        "name": "<string: tool name>",
        "description": "<string: tool description>",
        "input_schema": { "<JSON Schema object>" }
    }
]
```

**Constraints**:
- File permissions: `0o600` (owner only)
- File is created by parent process before bridge startup
- File is deleted by parent process during cleanup
