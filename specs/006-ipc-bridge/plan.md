# Implementation Plan: IPC Bridge

**Branch**: `006-ipc-bridge` | **Date**: 2026-02-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-ipc-bridge/spec.md`

## Summary

`set_agent_toolsets()` で登録した pydantic-ai ツールを、CLI バージョンに依存せず利用可能にする IPC ブリッジ機構を実装する。CLI が `type: "sdk"` の MCP サーバーを認識しない問題を、`McpStdioServerConfig`（`type: "stdio"`）を使ったブリッジプロセス経由の通信で解決する。親プロセス側に Unix domain socket ベースの IPC サーバーを起動し、CLI が subprocess として起動するブリッジプロセスが MCP プロトコル（stdin/stdout）と IPC（Unix socket）の間を中継する。

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: pydantic-ai>=1.42.0, claude-agent-sdk>=0.1.20, mcp>=1.0.0（新規追加）
**Storage**: 一時ファイル（ツールスキーマ）、Unix domain socket
**Testing**: pytest, pytest-asyncio
**Target Platform**: Linux, macOS（Unix domain socket 対応プラットフォーム）
**Project Type**: Library
**Performance Goals**: IPC ラウンドトリップ < 10ms（ツール実行時間除く）、ブリッジ起動 < 500ms
**Constraints**: Unix 系 OS のみ（Windows 初期スコープ外）
**Scale/Scope**: 既存ライブラリへの機能追加。新規 3 モジュール + 既存 3 ファイル修正

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Check

| Article | Status | Notes |
|---------|--------|-------|
| Art.1 Test-First | ✅ PASS | TDD で実装予定 |
| Art.2 Documentation | ✅ PASS | spec.md で仕様確定済み |
| Art.3 Library API Design | ✅ PASS | `set_agent_toolsets()` の API 後方互換性維持（FR-011）、新規例外クラス追加 |
| Art.4 Simplicity | ⚠️ REVIEW | 新規 `ipc/` パッケージ（3モジュール）の追加。各モジュールの必要性を正当化済み |
| Art.5 Code Quality | ✅ PASS | ruff + mypy チェック実施予定 |
| Art.6 Data Accuracy | ✅ PASS | 定数はすべて名前付き定数。環境依存値なし |
| Art.7 DRY | ✅ PASS | 既存の `mcp_integration.py` のツール変換パイプラインを再利用 |
| Art.8 Refactoring | ✅ PASS | 既存 `set_agent_toolsets()` を直接修正（V2 作成なし） |
| Art.9 Type Safety | ✅ PASS | 全関数に型注釈、`Any` 型不使用 |
| Art.10 Docstrings | ✅ PASS | Google-style docstring 適用 |
| Art.11 Naming | ✅ PASS | ブランチ名 `006-ipc-bridge` は規約準拠 |

### Post-Design Check

| Article | Status | Notes |
|---------|--------|-------|
| Art.4 Simplicity | ✅ PASS | `ipc/server.py`: IPC サーバー（新規能力）、`ipc/bridge.py`: MCP↔IPC中継（新規能力）、`ipc/protocol.py`: 共有型定義（server/bridge の両方から import）。各モジュールに固有の責務があり、統合すると循環依存のリスクがある |
| Art.7 DRY | ✅ PASS | `create_tool_wrapper()` を IPC サーバーのツールハンドラとして再利用。ToolSchema の JSON 構造は `ToolDefinition` と一致 |

## Project Structure

### Documentation (this feature)

```text
specs/006-ipc-bridge/
├── plan.md              # This file
├── research.md          # Phase 0: 技術調査結果
├── data-model.md        # Phase 1: エンティティ定義
├── quickstart.md        # Phase 1: 使用ガイド
├── contracts/           # Phase 1: インターフェース契約
│   ├── ipc-protocol.md  # IPC プロトコル仕様
│   └── public-api.md    # 公開 API 変更仕様
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/claudecode_model/
├── ipc/                        # [NEW] IPC ブリッジパッケージ
│   ├── __init__.py             # 公開 API: TransportType, DEFAULT_TRANSPORT, IPCSession
│   ├── server.py               # IPCServer: Unix socket サーバー（親プロセス側）
│   ├── bridge.py               # ブリッジプロセス: MCP stdio ↔ IPC 中継 (-m エントリポイント)
│   └── protocol.py             # IPC プロトコル: メッセージ型、フレーミング、シリアライズ
├── model.py                    # [MODIFY] set_agent_toolsets() に transport 追加、IPC ライフサイクル管理
├── mcp_integration.py          # [MODIFY] McpStdioServerConfig 生成サポート
├── exceptions.py               # [MODIFY] IPC 例外クラス追加
├── __init__.py                 # [MODIFY] 新規エクスポート追加
└── ... (他の既存ファイルは変更なし)

tests/
├── test_ipc_server.py          # [NEW] IPC サーバーのユニットテスト
├── test_ipc_bridge.py          # [NEW] ブリッジプロセスのユニットテスト
├── test_ipc_protocol.py        # [NEW] プロトコルのユニットテスト
├── test_ipc_integration.py     # [NEW] IPC 統合テスト（サーバー + ブリッジ）
└── ... (既存テストファイルは変更なし)

pyproject.toml                  # [MODIFY] mcp>=1.0.0 依存追加
```

**Structure Decision**: 既存の単一プロジェクト構造に `ipc/` サブパッケージを追加。IPC ブリッジは独立した通信層であり、既存モジュール（`mcp_integration.py`, `tool_converter.py`）とは責務が異なるため、サブパッケージとして分離する。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `ipc/` パッケージ新設（3モジュール） | IPC サーバー、ブリッジプロセス、共有プロトコルは各々固有の責務を持つ。ブリッジは `python -m` で独立プロセスとして実行される | 単一ファイルに全機能を統合すると 500 行超の巨大モジュールになり、独立プロセスとしての起動が困難 |
