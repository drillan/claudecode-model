# Feature Specification: Project Architecture

**Feature Branch**: `001-architecture`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Parent Spec (Category)
**Input**: User description: "現在の実装からアーキテクチャ仕様を定義"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - pydantic-ai Agent からの利用 (Priority: P1)

開発者は pydantic-ai の `Agent` に `ClaudeCodeModel` を渡し、Claude Code CLI の機能を pydantic-ai のインターフェースで利用する。テキスト応答・構造化出力・ツール実行を統一的に扱える。

**Why this priority**: プロジェクトの存在意義そのもの。pydantic-ai Model インターフェースの実装がなければ他の機能は成立しない。

**Independent Test**: `Agent(ClaudeCodeModel())` を生成し、`agent.run_sync("Hello")` でテキスト応答を取得できる。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeModel が初期化されている, **When** pydantic-ai Agent 経由でテキストプロンプトを送信する, **Then** テキスト応答が ModelResponse として返される
2. **Given** result_type に Pydantic BaseModel を指定した Agent, **When** プロンプトを送信する, **Then** JSON スキーマによる構造化出力が返される
3. **Given** Agent に function tools が登録されている, **When** ツール呼び出しを必要とするプロンプトを送信する, **Then** ツールが MCP サーバー経由で実行され結果が返される

---

### User Story 2 - ツール連携によるエージェント構築 (Priority: P2)

開発者は `@agent.tool_plain` / `@agent.tool` で定義した関数を Claude Code エージェントから呼び出し可能にする。pydantic-ai のツール定義が MCP サーバーに変換され、Claude Agent SDK 経由で利用される。

**Why this priority**: ツール連携なしでは単純なテキスト応答のみとなり、エージェントとしての価値が大幅に制限される。

**Independent Test**: `@agent.tool_plain` でツールを定義し、`model.set_agent_toolsets(agent._function_toolset)` を呼び出した後、ツール呼び出しを含むプロンプトでツールが実行される。

**Acceptance Scenarios**:

1. **Given** `@agent.tool_plain` で登録されたツール, **When** `set_agent_toolsets()` で MCP サーバーに変換する, **Then** Claude Code CLI からツールを呼び出し可能になる
2. **Given** 依存関係を持つツール (`@agent.tool` + `RunContext`), **When** `convert_tool_with_deps()` でシリアライザブルな依存関係を注入する, **Then** ツール実行時に依存関係がコンテキストとして提供される

---

### User Story 3 - レスポンスメタデータの取得 (Priority: P3)

開発者は SDK から返されるメタデータ（コスト、トークン使用量、ターン数、セッション ID）を取得し、モニタリングやコスト管理に活用する。

**Why this priority**: 本番環境でのコスト管理・パフォーマンス監視に必要だが、基本機能が動作した後に対応可能。

**Independent Test**: `request_with_metadata()` を呼び出し、`cli_response.total_cost_usd` および `cli_response.usage` にアクセスできる。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeModel が初期化されている, **When** `request_with_metadata()` を呼び出す, **Then** `RequestWithMetadataResult` が返され、ModelResponse と CLIResponse の両方にアクセスできる
2. **Given** 実行が完了した CLIResponse, **When** usage フィールドにアクセスする, **Then** input_tokens, output_tokens, cache 関連トークン数が取得できる

---

### Edge Cases

- SDK が未知のメッセージ型を返した場合、警告ログを出力しスキップする（`_sdk_compat.py` のパッチ）
- 構造化出力で SDK がスキーマ不一致を返した場合、ToolUseBlock 入力からのリカバリーを試みる
- タイムアウト発生時、async generator を適切にクローズしてサブプロセスをリークさせない
- `resume` と `continue_conversation` が同時に指定された場合、ValueError を送出する

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは pydantic-ai の `Model` インターフェース（`request()`, `request_stream()`）を実装しなければならない
- **FR-002**: システムは Claude Agent SDK の `query()` 関数を通じて Claude Code CLI を呼び出さなければならない
- **FR-003**: システムは pydantic-ai のツール定義を MCP サーバー形式に変換し、SDK 経由で公開しなければならない
- **FR-004**: システムは `--json-schema` オプションによる構造化出力をサポートしなければならない
- **FR-005**: システムは SDK の `ResultMessage` を pydantic-ai の `ModelResponse` に変換しなければならない
- **FR-006**: システムは全てのエラーを構造化された例外階層（`ClaudeCodeError` 派生）で伝播しなければならない
- **FR-007**: システムはタイムアウト、割り込み（Ctrl-C）、SDK エラーに対して適切なクリーンアップを行わなければならない
- **FR-008**: システムは中間メッセージのコールバック（同期・非同期両対応）をサポートしなければならない
- **FR-009**: システムは CLI サブプロセス実行モード（`ClaudeCodeCLI`）と SDK 直接呼び出しモード（`ClaudeCodeModel`）の2つのインターフェースを提供しなければならない
- **FR-010**: システムはシリアライザブルな依存関係の注入（`DepsContext`）をサポートしなければならない（実験的機能）

### Key Entities

- **ClaudeCodeModel**: pydantic-ai Model インターフェースの実装。SDK query の実行、ツール管理、レスポンス変換を統括するメインクラス
- **ClaudeCodeCLI**: CLI サブプロセスを直接実行する低レベルインターフェース。コマンド構築、プロセス管理、レスポンスパースを担当
- **CLIResponse**: SDK/CLI からのレスポンスを統一的に表現するデータモデル。メタデータ（コスト、トークン、セッション等）を保持
- **MCP Server**: pydantic-ai ツールを Claude Code CLI から呼び出し可能な形式に変換する仮想 MCP サーバー
- **DepsContext**: pydantic-ai の RunContext を簡略化した依存関係注入コンテナ（実験的）

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: pydantic-ai Agent 経由のテキスト応答リクエストが成功する
- **SC-002**: `result_type` 指定による構造化出力が pydantic-ai のバリデーションを通過する
- **SC-003**: `@agent.tool_plain` で定義したツールが Claude Code エージェントから呼び出し可能である
- **SC-004**: タイムアウト時に `CLIExecutionError(error_type="timeout")` が送出され、サブプロセスがリークしない
- **SC-005**: `request_with_metadata()` で取得した CLIResponse からコスト・トークン・セッション情報にアクセスできる
- **SC-006**: 全てのパブリック関数・メソッドに型注釈が付与されている

## Architecture Overview

### Module Structure

```
src/claudecode_model/
  __init__.py            # パブリック API エクスポート、ログ設定
  model.py               # ClaudeCodeModel (pydantic-ai Model 実装)
  cli.py                 # ClaudeCodeCLI (CLI サブプロセス実行)
  types.py               # 型定義 (CLIResponse, CLIUsage, Settings 等)
  exceptions.py          # 例外階層 (ClaudeCodeError 派生)
  mcp_integration.py     # ツール→MCP サーバー変換
  tool_converter.py      # pydantic-ai Tool→SdkMcpTool 変換
  response_converter.py  # SDK メッセージ→CLIResponse 変換
  deps_support.py        # シリアライザブル依存関係サポート（実験的）
  json_utils.py          # JSON 抽出ユーティリティ
  _sdk_compat.py         # SDK 互換パッチ（未知メッセージ型対応）
```

### Data Flow

```
pydantic-ai Agent
    │
    ▼
ClaudeCodeModel.request()
    │
    ├── _extract_system_prompt() / _extract_user_prompt()
    ├── _extract_model_settings()
    ├── _extract_json_schema()
    ├── _process_function_tools()  ──► MCP Server 更新
    │       │
    │       └── mcp_integration.py
    │           └── tool_converter.py
    │
    ├── _build_agent_options()  ──► ClaudeAgentOptions 構築
    │
    └── _execute_sdk_query()
            │
            ▼
        Claude Agent SDK query()
            │
            ├── 中間メッセージ  ──► message_callback
            │
            └── ResultMessage
                    │
                    ▼
            _result_message_to_cli_response()
                    │
                    ▼
                CLIResponse
                    │
                    ▼
            to_model_response()
                    │
                    ▼
            pydantic-ai ModelResponse
```

### Dependency Graph

```
model.py ─────► cli.py (定数のみ)
    │
    ├──► types.py
    ├──► exceptions.py
    ├──► mcp_integration.py ──► types.py (JsonValue)
    └──► _sdk_compat.py (副作用インポート)

tool_converter.py ──► deps_support.py
response_converter.py ──► types.py
json_utils.py ──► types.py (JsonValue 型のみ)
```

### External Dependencies

- **pydantic-ai** (>=1.42.0): Model インターフェース、Agent、ツールフレームワーク
- **claude-agent-sdk** (>=0.1.20): Claude Code CLI への SDK アクセス（query()、MCP サーバー等）
- **dacite** (>=1.9.0): dataclass デシリアライゼーション（deps_support.py で使用）

## Design Principles

1. **pydantic-ai ファースト**: pydantic-ai の Model インターフェースを忠実に実装し、Agent エコシステムとシームレスに統合する
2. **明示的エラー伝播**: 全てのエラーは構造化された例外として伝播する。暗黙的な抑制・デフォルト値代入は禁止
3. **型安全**: 全パブリック API に型注釈を付与。`Any` 型の使用は禁止
4. **SDK ブリッジパターン**: Claude Agent SDK の API を pydantic-ai の型システムに変換するブリッジとして機能する
5. **MCP ツール変換**: pydantic-ai のツール定義を MCP プロトコルに変換し、Claude Code CLI のツールシステムと統合する

## Child Spec Categories

| Category | Scope | Related Modules |
|----------|-------|-----------------|
| 002-core | pydantic-ai Model 実装、request/stream API、セッション管理 | `model.py`, `types.py`, `exceptions.py`, `cli.py` |
| 003-sdk | Claude Agent SDK 統合、レスポンス変換、互換パッチ | `response_converter.py`, `_sdk_compat.py` |
| 004-tools | MCP サーバー、ツール変換、AgentToolset、依存関係シリアライズ | `mcp_integration.py`, `tool_converter.py`, `deps_support.py` |
| 005-dx | エラーメッセージ、ログ、ドキュメント、テストインフラ | `json_utils.py`, SpecKit, CI/CD |
