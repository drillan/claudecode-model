# Quickstart: IPC Bridge

**Feature Branch**: `006-ipc-bridge`
**Date**: 2026-02-22

## Overview

IPC ブリッジにより、`set_agent_toolsets()` で登録した pydantic-ai ツールが CLI バージョンに依存せず利用可能になります。

## Basic Usage

```python
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

# 1. モデル作成
model = ClaudeCodeModel()

# 2. Agent 作成（ツール付き）
agent = Agent(model, tools=[my_tool_func])

# 3. ツールセット登録（transport はデフォルトで "auto" = IPC ブリッジ使用）
model.set_agent_toolsets(agent._function_toolset)

# 4. 実行（IPC サーバーは自動で起動・停止される）
result = await agent.run("Execute the tool")
```

## Transport Selection

```python
# IPC ブリッジ方式（デフォルト）
model.set_agent_toolsets(toolsets, transport="auto")   # "stdio" と同等
model.set_agent_toolsets(toolsets, transport="stdio")   # 明示的に IPC ブリッジ

# 従来の SDK 方式（CLI が type: "sdk" をサポートする場合）
model.set_agent_toolsets(toolsets, transport="sdk")
```

## What Happens Under the Hood

1. `set_agent_toolsets(transport="stdio")` が呼ばれると:
   - ツールスキーマが一時ファイルに書き出される
   - `McpStdioServerConfig` が生成される（ブリッジプロセスのコマンド含む）

2. `model.request()` / `agent.run()` が呼ばれると:
   - IPC サーバーが Unix domain socket 上で起動
   - SDK が CLI を起動し、CLI がブリッジプロセスを subprocess として起動
   - ブリッジは `tools/list` にローカルスキーマで応答
   - ブリッジは `tools/call` を IPC 経由で親プロセスに中継
   - ツール関数は親プロセス内で実行（コンテキスト保持）
   - リクエスト完了後、IPC サーバーとソケットファイルが自動クリーンアップ

## Error Handling

```python
from claudecode_model import IPCError, IPCToolExecutionError

try:
    result = await agent.run("Execute the tool")
except IPCToolExecutionError as e:
    # ツール関数内で発生した例外
    print(f"Tool execution failed: {e}")
except IPCError as e:
    # IPC 通信エラー（接続失敗、メッセージサイズ超過等）
    print(f"IPC error: {e}")
```

## Prerequisites

- Python 3.13+
- `mcp>=1.0.0`（`pyproject.toml` に明示的に追加される）
- Unix 系 OS（Linux, macOS）
