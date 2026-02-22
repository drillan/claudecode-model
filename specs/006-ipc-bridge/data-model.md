# Data Model: IPC Bridge

**Feature Branch**: `006-ipc-bridge`
**Date**: 2026-02-22

## Entities

### TransportType

ツール通信のトランスポート方式を表す型エイリアス。

```python
type TransportType = Literal["auto", "stdio", "sdk"]
```

| 値 | 説明 |
|------|------|
| `"auto"` | デフォルト。現時点では `"stdio"` と同等に動作 |
| `"stdio"` | IPC ブリッジ方式（Unix domain socket 経由） |
| `"sdk"` | 従来の SDK 方式（`McpSdkServerConfig`） |

**制約**: `"auto"` は将来の CLI バージョン検出を想定しているが、初期実装では静的に `"stdio"` に解決される。

---

### IPCRequest

ブリッジプロセスから親プロセスへ送信されるリクエストメッセージ。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `method` | `Literal["call_tool"]` | Yes | メソッド名 |
| `params` | `CallToolParams` | Yes | メソッドパラメータ |

**制約**:
- 初期実装では `method` は `"call_tool"` のみ
- `tools/list` はブリッジ側ローカルで処理するため IPC リクエストにはならない
- シリアライズ後のサイズが `MAX_MESSAGE_SIZE` を超えてはならない

---

### CallToolParams

`call_tool` リクエストのパラメータ。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `name` | `str` | Yes | ツール名 |
| `arguments` | `dict[str, JsonValue]` | Yes | ツール引数 |

**制約**:
- `name` は登録済みツール名と一致する必要がある
- `arguments` はツールの JSON Schema に適合する必要がある

---

### IPCResponse

親プロセスからブリッジプロセスへ返送される成功レスポンス。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `result` | `ToolResult` | Yes | ツール実行結果 |

**制約**:
- `result` または `error` のどちらか一方のみを含む（相互排他は `IPCResponse | IPCErrorResponse` の Union で表現）

---

### ToolResult

ツール実行結果。MCP `CallToolResult` に準拠。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `content` | `list[ToolResultContent]` | Yes | 結果コンテンツ |
| `isError` | `bool` | No | エラーフラグ（デフォルト: `false`） |

---

### ToolResultContent

ツール結果のコンテンツブロック。MCP `TextContent` に準拠。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `type` | `Literal["text"]` | Yes | コンテンツ種別 |
| `text` | `str` | Yes | テキスト内容 |

---

### IPCErrorResponse

親プロセスからブリッジプロセスへ返送されるエラーレスポンス。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `error` | `IPCErrorPayload` | Yes | エラー情報 |

---

### IPCErrorPayload

IPC エラー情報（ワイヤプロトコル上の構造体。Python 例外クラス `IPCError` とは別物）。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `message` | `str` | Yes | エラーメッセージ |
| `type` | `str` | Yes | エラー種別（例外クラス名） |

---

### ToolSchema

ブリッジプロセスに渡されるツールスキーマ。一時ファイル経由で JSON として受け渡される。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `name` | `str` | Yes | ツール名 |
| `description` | `str` | Yes | ツール説明 |
| `input_schema` | `dict[str, JsonValue]` | Yes | 入力パラメータの JSON Schema |

**制約**:
- ブリッジプロセスは起動時にスキーマファイルを読み込み、以降は `tools/list` 応答に使用
- スキーマファイルのフォーマットは `list[ToolSchema]` の JSON 配列

---

### IPCSession

IPC セッションの状態を管理する内部エンティティ（永続化なし）。

| フィールド | 型 | 必須 | 説明 |
|------------|------|------|------|
| `socket_path` | `Path` | Yes | Unix socket ファイルのパス |
| `schema_path` | `Path` | Yes | ツールスキーマ一時ファイルのパス |
| `tool_handlers` | `dict[str, ToolHandler]` | Yes | ツール名→実行関数のマッピング |
| `server` | `asyncio.Server \| None` | No | 稼働中の asyncio サーバー |

**状態遷移**:
```
Created → Started → Stopped
              ↓
          (exception)
              ↓
           Stopped (cleanup guaranteed)
```

**制約**:
- `socket_path` は UUID を含むため衝突しない
- `socket_path` のパーミッションは `0o600`（owner only）
- `schema_path` のパーミッションは `0o600`（owner only）
- `Stopped` 状態で `socket_path` と `schema_path` が削除される

---

### ToolHandler

ツール実行関数の型エイリアス。

```python
type ToolHandler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]
```

既存の `mcp_integration.create_tool_wrapper()` が生成するラッパー関数と同じシグネチャ。
戻り値は MCP 互換形式の `dict`（例: `{"content": [{"type": "text", "text": "..."}]}`）。

---

## 定数

| 定数名 | 型 | 値 | 説明 |
|--------|------|-----|------|
| `MAX_MESSAGE_SIZE` | `int` | `10_485_760` (10 MB) | IPC メッセージの最大サイズ（バイト） |
| `SOCKET_PERMISSIONS` | `int` | `0o600` | ソケットファイルのパーミッション |
| `SCHEMA_FILE_PREFIX` | `str` | `"claudecode_ipc_schema_"` | スキーマ一時ファイルのプレフィックス |
| `SOCKET_FILE_PREFIX` | `str` | `"claudecode_ipc_"` | ソケットファイルのプレフィックス |
| `SOCKET_FILE_SUFFIX` | `str` | `".sock"` | ソケットファイルのサフィックス |
| `LENGTH_PREFIX_SIZE` | `int` | `4` | メッセージ長プレフィックスのバイト数 |
| `DEFAULT_TRANSPORT` | `TransportType` | `"auto"` | デフォルトのトランスポート方式 |

---

## 関係図

```
ClaudeCodeModel
  │
  ├── set_agent_toolsets(transport)
  │     │
  │     ├── transport="sdk" → McpSdkServerConfig (既存)
  │     │
  │     └── transport="stdio"/"auto"
  │           │
  │           ├── ToolSchema[] → schema temp file
  │           ├── socket_path → generated
  │           └── McpStdioServerConfig
  │                 command: sys.executable
  │                 args: [-m, claudecode_model.ipc.bridge, socket_path, schema_path]
  │
  ├── request() / stream_messages() / request_with_metadata()
  │     │
  │     ├── _start_ipc_server() → IPCSession.start()
  │     │     └── asyncio.start_unix_server(socket_path)
  │     │
  │     ├── SDK query() → CLI → Bridge process
  │     │     │
  │     │     ├── Bridge: tools/list → local ToolSchema[]
  │     │     │
  │     │     └── Bridge: tools/call
  │     │           │
  │     │           ├── IPCRequest → Unix socket → Parent
  │     │           │
  │     │           ├── Parent: ToolHandler(arguments)
  │     │           │
  │     │           └── IPCResponse ← Unix socket ← Parent
  │     │
  │     └── _stop_ipc_server() → IPCSession.stop()
  │           ├── server.close()
  │           ├── unlink(socket_path)
  │           └── unlink(schema_path)
  │
  └── _process_function_tools()
        └── ツールフィルタ → MCP設定再生成
```

---

## 例外

### 新規例外クラス

| 例外 | 親クラス | 用途 |
|------|----------|------|
| `IPCError` | `ClaudeCodeError` | IPC 通信の基底例外 |
| `IPCConnectionError` | `IPCError` | ブリッジが IPC サーバーに接続できない |
| `IPCMessageSizeError` | `IPCError` | メッセージサイズが `MAX_MESSAGE_SIZE` を超過 |
| `IPCToolExecutionError` | `IPCError` | ツール関数実行中のエラー |
| `BridgeStartupError` | `IPCError` | ブリッジプロセスの起動失敗 |

**注**: ワイヤプロトコル上のエラー構造体は `IPCErrorPayload` と命名し、Python 例外クラス `IPCError` との混同を防止する。
