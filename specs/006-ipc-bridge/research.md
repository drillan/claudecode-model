# Research: IPC Bridge

**Feature Branch**: `006-ipc-bridge`
**Date**: 2026-02-22

## Research Task 1: ツールスキーマの受け渡し方式

### Context

ブリッジプロセスは CLI が subprocess として起動する。起動時にツールスキーマを受け取り、`tools/list` に応答する必要がある（IPC 不要）。受け渡し方式を決定する。

### Decision: 一時ファイル方式

### Rationale

- コマンドライン引数: OS により上限あり（Linux: 約 2MB、macOS: 約 256KB）。大量のツールスキーマには不十分
- 環境変数: 同様のサイズ制限（通常 128KB 程度）
- 一時ファイル: サイズ制限なし。`tempfile` モジュールで安全に管理可能

### Alternatives Considered

| 方式 | 長所 | 短所 | 判定 |
|------|------|------|------|
| コマンドライン引数（JSON 直渡し） | シンプル | サイズ制限あり、プロセス一覧で内容が見える | 却下 |
| 環境変数 | シンプル | サイズ制限あり | 却下 |
| 一時ファイル | サイズ無制限、セキュア（パーミッション制御可能） | ファイル管理が必要 | **採用** |
| stdin パイプ | サイズ無制限 | MCP の stdin と競合 | 却下 |

### Implementation Notes

- 一時ファイルは親プロセスが作成・管理し、IPC セッション終了時に削除
- ファイルパスはコマンドライン引数としてブリッジプロセスに渡す
- パーミッションは owner only (`0o600`)

---

## Research Task 2: IPC プロトコル設計

### Context

親プロセスとブリッジプロセス間の通信プロトコルを設計する。`call_tool` リクエスト/レスポンスのみをサポートする（`list_tools` はブリッジ側ローカルで処理）。

### Decision: 長さプレフィックス付き JSON メッセージ

### Rationale

- JSON-RPC 2.0 はオーバーヘッドが大きい（ID 管理、バッチ処理等が不要）
- 直列化のみのため、リクエスト ID ベースの多重化は不要
- 長さプレフィックス方式はメッセージ境界の判定が確実

### Protocol Format

```
[4 bytes: payload length (big-endian uint32)][payload: UTF-8 JSON]
```

### Message Types

**Request** (bridge → parent):
```json
{
    "method": "call_tool",
    "params": {
        "name": "tool_name",
        "arguments": {"arg1": "value1"}
    }
}
```

**Success Response** (parent → bridge):
```json
{
    "result": {
        "content": [{"type": "text", "text": "result_text"}],
        "isError": false
    }
}
```

**Error Response** (parent → bridge):
```json
{
    "error": {
        "message": "Error description",
        "type": "ToolExecutionError"
    }
}
```

### Alternatives Considered

| 方式 | 長所 | 短所 | 判定 |
|------|------|------|------|
| JSON-RPC 2.0 | 標準プロトコル | 過剰設計（ID、バッチ不要） | 却下 |
| 改行区切り JSON (NDJSON) | シンプル | ペイロードに改行がある場合に問題 | 却下 |
| 長さプレフィックス JSON | メッセージ境界が確実、シンプル | 独自プロトコル | **採用** |
| Protocol Buffers | 高性能 | 追加依存、過剰設計 | 却下 |

---

## Research Task 3: IPC サーバー実装方式

### Context

親プロセス側の IPC サーバーの実装方式を決定する。

### Decision: `asyncio.start_unix_server` (標準ライブラリ)

### Rationale

- asyncio は既にプロジェクト全体で使用されている（`anyio` 経由）
- 追加依存なし
- Unix domain socket は対象プラットフォーム（Linux, macOS）で標準サポート
- パフォーマンス要件（10ms 以下のラウンドトリップ）を容易に満たせる

### Alternatives Considered

| 方式 | 長所 | 短所 | 判定 |
|------|------|------|------|
| `asyncio.start_unix_server` | 標準ライブラリ、async 対応 | 低レベル API | **採用** |
| `anyio` の Unix socket API | プロジェクトの async 基盤と一貫 | Unix socket サポートは限定的 | 却下 |
| `aiohttp` Unix socket | 高レベル API | 追加依存、HTTP は過剰 | 却下 |
| `zmq` (ZeroMQ) | 高性能 | 追加依存 | 却下 |

### Implementation Notes

- `asyncio.start_unix_server` で接続を待機
- 各接続はリクエスト→レスポンスの1往復で完結（直列化のため、接続を使い回す必要はない）
- ただし、パフォーマンス最適化として接続の持続化も検討可能（後述の Research Task 7 参照）

---

## Research Task 4: ブリッジプロセスの MCP サーバー実装

### Context

ブリッジプロセスは CLI から見て標準的な stdio MCP サーバーとして動作する必要がある（FR-003）。

### Decision: `mcp.server.Server` + `mcp.server.stdio.stdio_server`

### Rationale

- `mcp` ライブラリは `claude-agent-sdk` の推移的依存で利用可能（`mcp>=0.1.0`、実際は `1.26.0` インストール済み）
- FR-013 に基づき明示的な依存として宣言する
- `mcp.server.Server` は `@list_tools()` と `@call_tool()` デコレータを提供
- `mcp.server.stdio.stdio_server` は stdin/stdout のトランスポートを提供

### Key API Usage

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("bridge")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return loaded_tools  # スキーマファイルから読み込み済み

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # IPC 経由で親プロセスに中継
    result = await ipc_client.call(name, arguments)
    return result
```

### Alternatives Considered

| 方式 | 長所 | 短所 | 判定 |
|------|------|------|------|
| `mcp.server.Server` | 公式 MCP 実装、デコレータ API | ライブラリ依存 | **採用** |
| `mcp.server.FastMCP` | より高レベル API | 不要な機能が多い | 却下 |
| 独自 JSON-RPC 2.0 実装 | 依存なし | MCP プロトコルの正確な実装が困難 | 却下 |

---

## Research Task 5: IPC メッセージサイズ制限

### Context

FR-006: IPC 通信のメッセージに最大サイズ制限を設ける。超過時は明示的エラー。

### Decision: 10 MB (10,485,760 bytes)

### Rationale

- ツールの引数や戻り値は通常数 KB～数十 KB
- 大きな JSON レスポンスでも数 MB が実用的な上限
- 10 MB は十分な余裕を持ちつつ、メモリ使用量を制限する妥当な値
- 長さプレフィックスは 4 バイト（uint32）で最大約 4 GB を表現可能だが、アプリケーションレベルで制限

### Alternatives Considered

| サイズ | 評価 |
|--------|------|
| 1 MB | 大きなツール結果で不足する可能性あり |
| 10 MB | 十分な余裕がありつつ現実的 → **採用** |
| 100 MB | メモリ使用量が過大 |
| 無制限 | メモリ枯渇リスク |

---

## Research Task 6: ソケットファイル管理

### Context

FR-009（パーミッション）、FR-010（stale ファイル検出）に関するベストプラクティス。

### Decision

- パス: `tempfile.gettempdir()` 配下に `claudecode_ipc_<uuid>.sock` 形式
- パーミッション: `0o600`（owner only）
- stale 検出: サーバー起動時に既存ソケットファイルの存在をチェックし、接続テストで生死判定

### Implementation Details

1. **ソケットパス生成**:
   ```python
   import tempfile, uuid
   socket_path = Path(tempfile.gettempdir()) / f"claudecode_ipc_{uuid.uuid4().hex}.sock"
   ```

2. **パーミッション設定**:
   - `asyncio.start_unix_server` のバインド後、`os.chmod(socket_path, 0o600)` を実行

3. **stale ファイル検出**:
   - ソケットパスに UUID を含めるため、同一パスの衝突は事実上発生しない
   - 前回の異常終了で残った stale ファイルは、新しい UUID で別パスに作成されるため影響しない
   - ただし、一時ディレクトリのクリーンアップとして、古い `claudecode_ipc_*.sock` ファイルを起動時に検出・除去する

### Alternatives Considered

| 方式 | 評価 |
|------|------|
| 固定パス + PID ファイル | PID 再利用の誤判定リスク |
| UUID パス | 衝突なし、stale 問題を根本的に回避 → **採用** |
| 抽象ソケット（Linux only） | macOS 非対応 |

---

## Research Task 7: IPC 接続モデル

### Context

ブリッジプロセスの IPC 接続はどのタイミングで確立すべきか。仕様では「lazy connect」（`tools/call` 時に初めて確立）と記載。

### Decision: Lazy connect + 接続持続

### Rationale

- `tools/list` 時点では IPC 不要（ローカルスキーマで応答）
- 初回の `tools/call` で接続を確立し、以降は同一接続を再利用
- Unix socket 接続確立のオーバーヘッドは微小だが、接続持続の方が効率的
- 1 リクエスト内で複数のツール呼び出しが発生する場合にメリットがある

### Implementation Notes

- ブリッジプロセス側で `asyncio.open_unix_connection()` を使用
- 接続は初回 `call_tool` 時に確立、以降再利用
- 接続切断時はエラーとして報告（再接続は行わない）

---

## Research Task 8: `_process_function_tools()` と IPC の同期/非同期ギャップ

### Context

FR-012: `_process_function_tools()` は同期メソッドだが、IPC サーバーの停止/再構築は非同期処理。

### Decision: MCP 設定の遅延適用

### Rationale

`_process_function_tools()` が同期メソッドである制約を考慮し、以下の戦略を採用:

1. `_process_function_tools()` はツールフィルタリングと MCP 設定の生成のみを行う（同期で完結）
2. 実際の IPC サーバー起動/停止は `request()` 等のライフサイクル内で行う（非同期）
3. IPC サーバーはリクエストごとに起動・停止するため、`_process_function_tools()` 時点での既存サーバー停止は不要

### Flow

```
request() / stream_messages() / request_with_metadata():
  1. _process_function_tools()     [sync] → ツールフィルタ + MCP設定更新
  2. _prepare_ipc_session()        [sync] → スキーマファイル書き出し + StdioConfig生成
  3. await _start_ipc_server()     [async] → Unix socket サーバー起動
  4. await _execute_sdk_query()    [async] → SDK クエリ実行
  5. await _stop_ipc_server()      [async/finally] → サーバー停止 + クリーンアップ
```

### Alternatives Considered

| 方式 | 評価 |
|------|------|
| `_process_function_tools()` を async 化 | pydantic-ai の API 互換性を破壊 |
| バックグラウンドタスクで旧サーバー停止 | 競合状態のリスク |
| リクエストごとに起動・停止 | シンプルで安全 → **採用** |

---

## Research Task 9: ブリッジプロセスのエントリポイント

### Context

ブリッジプロセスは `McpStdioServerConfig` の `command` / `args` で起動される。エントリポイントの設計。

### Decision: `python -m claudecode_model.ipc.bridge`

### Rationale

- `sys.executable` を使用して同一 Python 環境で起動
- `-m` オプションでモジュールとして実行（仮想環境の不整合を検出可能）
- 引数: `<socket_path> <schema_file_path>`

### McpStdioServerConfig

```python
McpStdioServerConfig(
    type="stdio",
    command=sys.executable,
    args=["-m", "claudecode_model.ipc.bridge", str(socket_path), str(schema_path)],
)
```

---

## Research Task 10: mcp ライブラリの依存宣言

### Context

FR-013: ブリッジプロセスが使用する MCP サーバーライブラリは、プロジェクトの明示的な依存関係として宣言されなければならない。

### Decision: `pyproject.toml` に `mcp>=1.0.0` を追加

### Rationale

- 現在 `mcp 1.26.0` がインストール済み（`claude-agent-sdk` の推移的依存）
- FR-013 は推移的依存への暗黙的な依存を禁止
- `mcp.server.Server` と `mcp.server.stdio.stdio_server` を使用するため、明示的に宣言が必要
- バージョンは `>=1.0.0` で十分（Server API は安定）

### Implementation

`pyproject.toml` の `[project.dependencies]` に追加:
```toml
"mcp>=1.0.0",
```
