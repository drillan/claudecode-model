# Feature Specification: Core Model Interface

**Feature Branch**: `002-core`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Parent Spec (Category)
**Parent Spec**: 001-architecture
**Input**: User description: "現在の実装から Core Model Interface のカテゴリ仕様を定義"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - pydantic-ai Agent 経由のテキスト応答 (Priority: P1)

開発者は `ClaudeCodeModel` を `pydantic-ai Agent` に渡し、テキストプロンプトに対するテキスト応答を取得する。`Model.request()` を通じて Claude Agent SDK の `query()` が呼び出され、結果が `ModelResponse` に変換される。

**Why this priority**: `request()` はプロジェクトの根幹機能。pydantic-ai Model インターフェースの中核メソッドであり、この機能なしに他の全ての機能は成立しない。

**Independent Test**: `Agent(ClaudeCodeModel())` を生成し、`agent.run_sync("Hello")` でテキスト応答が返されることを確認する。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeModel がデフォルト設定で初期化されている, **When** pydantic-ai Agent 経由でテキストプロンプトを送信する, **Then** テキスト応答が `ModelResponse(parts=[TextPart])` として返される
2. **Given** `model_settings` にタイムアウト・ワーキングディレクトリ等を指定している, **When** `request()` を呼び出す, **Then** 指定された設定が SDK クエリに反映される
3. **Given** メッセージリストにシステムプロンプトが含まれている, **When** `request()` を呼び出す, **Then** システムプロンプトが SDK オプションに設定される

---

### User Story 2 - 構造化出力（JSON Schema） (Priority: P1)

開発者は `result_type` に Pydantic BaseModel を指定し、Claude に構造化された JSON データを返させる。`ModelProfile` の `supports_json_schema_output=True` により pydantic-ai が自動的に JSON Schema を抽出し、`--json-schema` オプションとして SDK に渡される。

**Why this priority**: 構造化出力はエージェントアプリケーションの主要ユースケースであり、request() と並ぶ P1 機能。

**Independent Test**: `result_type=MyModel` を指定した Agent を作成し、JSON スキーマに準拠した構造化出力が pydantic バリデーションを通過することを確認する。

**Acceptance Scenarios**:

1. **Given** `result_type` に Pydantic BaseModel を指定した Agent, **When** プロンプトを送信する, **Then** `output_format={"type": "json_schema", "schema": ...}` が SDK オプションに設定される
2. **Given** SDK が `structured_output` フィールドを返した場合, **When** `to_model_response()` が呼ばれる, **Then** JSON シリアライズされた文字列が `TextPart.content` に設定される
3. **Given** SDK が `{"parameters": {...}}` ラッパー形式で出力を返した場合, **When** `_try_unwrap_parameters_wrapper()` が呼ばれる, **Then** ラッパーが自動的に除去され内部データが抽出される
4. **Given** SDK がスキーマ不一致で `error_max_structured_output_retries` を返した場合, **When** `ToolUseBlock` の captured input が存在する, **Then** captured input からのリカバリーが試みられる

---

### User Story 3 - メタデータ付きレスポンス取得 (Priority: P2)

開発者は `request_with_metadata()` を使用して、pydantic-ai の `ModelResponse` に加えて、SDK 固有のメタデータ（コスト、トークン使用量、ターン数、セッション ID）を取得する。

**Why this priority**: 本番環境でのコスト管理・パフォーマンス監視に必要だが、基本的な request/構造化出力が動作した後に対応可能。

**Independent Test**: `request_with_metadata()` を呼び出し、`result.cli_response.total_cost_usd` と `result.cli_response.usage` にアクセスできることを確認する。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeModel が初期化されている, **When** `request_with_metadata()` を呼び出す, **Then** `RequestWithMetadataResult(response=ModelResponse, cli_response=CLIResponse)` が返される
2. **Given** 実行が完了した CLIResponse, **When** `usage` フィールドにアクセスする, **Then** `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` が取得できる
3. **Given** 実行が完了した CLIResponse, **When** `total_cost_usd`, `duration_ms`, `session_id` にアクセスする, **Then** SDK から返された値が保持されている

---

### User Story 4 - メッセージストリーミング (Priority: P2)

開発者は `stream_messages()` を使用して、SDK クエリの中間メッセージ（AssistantMessage, ToolUseBlock 等）をリアルタイムで受信する。ストリーミング UI やプログレスインジケーターの構築に使用する。

**Why this priority**: リアルタイム UI 構築に必要だが、基本的な request が動作した後に対応可能。

**Independent Test**: `stream_messages()` を呼び出し、`async for message in ...` で中間メッセージと最終結果の両方を受信できることを確認する。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeModel が初期化されている, **When** `stream_messages()` を呼び出す, **Then** SDK の `query()` から yield されるメッセージが順次返される
2. **Given** ストリーミング中にタイムアウトが発生した場合, **When** `anyio.move_on_after` がキャンセルを検出する, **Then** async generator が適切にクローズされ `CLIExecutionError(error_type="timeout")` が送出される

---

### User Story 5 - セッション継続・再開 (Priority: P3)

開発者は `continue_conversation=True` または `resume=<session_id>` を使用して、以前のセッションを継続する。コンストラクタまたは `model_settings` 経由で指定可能。

**Why this priority**: 長時間タスクやインタラクティブなワークフローで有用だが、単発リクエストの基本機能が優先。

**Independent Test**: `continue_conversation=True` で2回目のリクエストを送信し、前回のコンテキストが維持されていることを確認する。

**Acceptance Scenarios**:

1. **Given** `continue_conversation=True` が設定されている, **When** `request()` を呼び出す, **Then** SDK オプションに `continue_conversation=True` が設定される
2. **Given** `resume=<session_id>` が `model_settings` に設定されている, **When** `request()` を呼び出す, **Then** SDK オプションに `resume=<session_id>` が設定される
3. **Given** `resume` と `continue_conversation` が同時に指定された場合, **When** `_extract_model_settings()` が呼ばれる, **Then** `ValueError` が送出される

---

### User Story 6 - CLI サブプロセス実行 (Priority: P3)

開発者は `ClaudeCodeCLI` を使用して、Claude Code CLI をサブプロセスとして直接実行する。SDK を使わない軽量なインターフェースであり、コマンド構築・プロセス管理・レスポンスパースを提供する。

**Why this priority**: SDK モードが主要インターフェースであり、CLI サブプロセスモードは補助的な位置づけ。

**Independent Test**: `ClaudeCodeCLI(model="claude-sonnet-4-5").execute("Hello")` を呼び出し、`CLIResponse` が返されることを確認する。

**Acceptance Scenarios**:

1. **Given** ClaudeCodeCLI がデフォルト設定で初期化されている, **When** `execute(prompt)` を呼び出す, **Then** CLI サブプロセスが実行され `CLIResponse` が返される
2. **Given** `json_schema` が設定されている, **When** `_build_command()` が呼ばれる, **Then** `--json-schema` フラグがコマンドに追加される
3. **Given** CLI 実行中にタイムアウトが発生した場合, **When** `asyncio.wait_for` がタイムアウトする, **Then** プロセスが kill され `CLIExecutionError(error_type="timeout")` が送出される
4. **Given** CLI 実行中に KeyboardInterrupt が発生した場合, **When** `interrupt_handler` が設定されている, **Then** ハンドラーの戻り値に応じて処理が続行または中断される

---

### Edge Cases

- `ResultMessage.usage` が `None` の場合、`CLIExecutionError` を送出すべきである。**現在の実装はデフォルト値 0 を代入しており、デザイン原則 #2（暗黙的な値の代入禁止）に違反している。子仕様で修正が必要。**
- `ResultMessage.result` と `structured_output` の両方が空の場合、`CLIResponse` のバリデーションで `ValueError` が送出される（ただし `error_` サブタイプは除外）
- SDK が未知の `error_` サブタイプを返した場合（`is_error=False`）、警告ログを出力する
- プロンプトが空または `MAX_PROMPT_LENGTH` を超える場合、`ValueError` が送出される
- `claude` CLI が見つからない場合、`CLINotFoundError` が送出される（解決方法を含むメッセージ付き）
- `model_settings` の型が不正な場合（例: `timeout` に文字列）、`TypeError` を送出すべきである。**現在の実装は `working_directory` のみ `TypeError` を送出し、他のフィールドは警告ログを出力して無視するという不整合がある。子仕様で統一が必要。**
- 構造化出力で `{"parameter": {...}}` や `{"output": {...}}` ラッパーが使われた場合も自動除去する

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは pydantic-ai の `Model` インターフェース（`request()`）を実装しなければならない。なお、pydantic-ai の `Model.request_stream()` は意図的に未実装であり、代替として `stream_messages()` を提供する（FR-008 参照）。`stream_messages()` は pydantic-ai の `StreamedResponse` ではなく SDK の `Message` を直接 yield する独自ストリーミングメソッドである
- **FR-002**: システムは Claude Agent SDK の `query()` 関数を通じてクエリを実行しなければならない
- **FR-003**: システムは `--json-schema` オプションによる構造化出力をサポートしなければならない
- **FR-004**: システムは SDK の `ResultMessage` を pydantic-ai の `ModelResponse` に変換しなければならない
- **FR-005**: システムはタイムアウト、割り込み（Ctrl-C）、SDK エラーに対して適切なクリーンアップを行わなければならない
- **FR-006**: システムは中間メッセージのコールバック（同期・非同期両対応）をサポートしなければならない
- **FR-007**: システムは `request_with_metadata()` で SDK メタデータ（コスト、トークン、セッション等）を公開しなければならない
- **FR-008**: システムは `stream_messages()` で中間メッセージのストリーミングをサポートしなければならない
- **FR-009**: システムは `ClaudeCodeModelSettings` で per-request のパラメータオーバーライドをサポートしなければならない
- **FR-010**: システムは `continue_conversation` / `resume` によるセッション継続をサポートしなければならない
- **FR-011**: システムは CLI サブプロセス実行モード（`ClaudeCodeCLI`）を提供しなければならない
- **FR-012**: システムは構造化出力のラッパー形式（`parameters`, `parameter`, `output`）を自動的に検出・除去しなければならない
- **FR-013**: システムは構造化出力リカバリーサブタイプ発生時に `ToolUseBlock` の captured input からのリカバリーを試みなければならない
- **FR-014**: システムは全てのエラーを構造化された例外階層（`ClaudeCodeError` 派生）で伝播しなければならない

### Key Entities

- **ClaudeCodeModel**: pydantic-ai `Model` インターフェースの実装クラス。SDK `query()` の実行、設定管理、レスポンス変換、ツール処理を統括する。コンストラクタで `model_name`, `working_directory`, `timeout`, `allowed_tools`, `disallowed_tools`, `permission_mode`, `max_turns`, `message_callback`, `continue_conversation`, `interrupt_handler` を受け取る
- **ClaudeCodeCLI**: CLI サブプロセスを直接実行する低レベルインターフェース。コマンド構築、プロセスライフサイクル管理（起動・タイムアウト・割り込み・終了）、JSON レスポンスパースを担当する
- **CLIResponse**: SDK/CLI からのレスポンスを統一的に表現する Pydantic モデル。`type`, `subtype`, `is_error`, `duration_ms`, `duration_api_ms`, `num_turns`, `result`, `session_id`, `total_cost_usd`, `usage`, `structured_output` 等のフィールドを持つ。`to_model_response()` で pydantic-ai `ModelResponse` に変換する
- **ClaudeCodeModelSettings**: pydantic-ai `ModelSettings` を拡張した TypedDict。`max_budget_usd`, `append_system_prompt`, `max_turns`, `working_directory`, `continue_conversation`, `resume` を追加する
- **CLIUsage**: トークン使用量情報を保持する Pydantic モデル。`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `server_tool_use`, `service_tier`, `cache_creation` を含む
- **RequestWithMetadataResult**: `ModelResponse` と `CLIResponse` の両方を返す NamedTuple。メタデータへのアクセスが必要な場合に使用する
- **例外階層**: `ClaudeCodeError` を基底とし、`CLINotFoundError`, `CLIExecutionError`（error_type/recoverable 属性付き）, `CLIInterruptedError`, `CLIResponseParseError`, `StructuredOutputError` 等の構造化例外を提供する

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: pydantic-ai Agent 経由のテキスト応答リクエストが成功する
- **SC-002**: `result_type` 指定による構造化出力が pydantic-ai のバリデーションを通過する
- **SC-003**: タイムアウト時に `CLIExecutionError(error_type="timeout")` が送出され、サブプロセス/async generator がリークしない
- **SC-004**: `request_with_metadata()` で取得した `CLIResponse` からコスト・トークン・セッション情報にアクセスできる
- **SC-005**: `stream_messages()` で中間メッセージがリアルタイムに受信できる
- **SC-006**: 全てのエラーが構造化例外として伝播し、エラーメッセージに解決方法が含まれる
- **SC-007**: 全てのパブリック関数・メソッドに型注釈が付与されている
- **SC-008**: `continue_conversation` と `resume` が排他的であり、同時指定時に `ValueError` が送出される
- **SC-009**: 構造化出力のラッパー形式（`parameters`, `parameter`, `output`）が自動除去される
- **SC-010**: CLI サブプロセスモードでプロンプト送信から `CLIResponse` 取得までの一連のフローが動作する

## Scope

### In Scope (002-core)

- `ClaudeCodeModel` クラスの `request()`, `request_with_metadata()`, `stream_messages()` メソッド
- `ClaudeCodeModel` のコンストラクタパラメータと `ModelProfile` の定義
- `ClaudeCodeModelSettings` による per-request パラメータオーバーライド
- `CLIResponse`, `CLIUsage`, `RequestWithMetadataResult` 等のレスポンス型定義
- `ClaudeCodeError` を基底とする例外階層
- `ClaudeCodeCLI` による CLI サブプロセス実行
- 構造化出力の抽出・ラッパー除去・リカバリーロジック
- セッション継続・再開の制御
- タイムアウト・割り込みのハンドリング

### Out of Scope (他カテゴリ)

- MCP サーバー変換・ツール変換（→ 004-tools）
- SDK メッセージ型の変換・互換パッチ（→ 003-sdk）
- エラーメッセージの UX・ログフォーマット・テストインフラ（→ 005-dx）

## Design Principles

1. **pydantic-ai Model 準拠**: pydantic-ai の `Model` インターフェースを忠実に実装し、Agent エコシステムとシームレスに統合する
2. **明示的エラー伝播**: 全てのエラーは構造化された例外として伝播する。暗黙的な値の代入や処理の抑制は禁止
3. **型安全**: 全パブリック API に型注釈を付与。`Any` 型の使用は禁止。`JsonValue` 再帰型でJSON互換値を表現する
4. **メタデータ保全**: SDK から返されるメタデータ（コスト、トークン、セッション等）を `CLIResponse` に保全し、`request_with_metadata()` で公開する
5. **タイムアウト安全**: タイムアウト発生時に async generator やサブプロセスが確実にクリーンアップされる
6. **設定の階層性**: コンストラクタでデフォルトを設定し、`model_settings` で per-request オーバーライドを可能にする

## Related Modules

| Module | Role |
|--------|------|
| `model.py` | ClaudeCodeModel - pydantic-ai Model 実装の中核 |
| `types.py` | CLIResponse, CLIUsage, ClaudeCodeModelSettings 等の型定義 |
| `exceptions.py` | ClaudeCodeError 派生の構造化例外階層 |
| `cli.py` | ClaudeCodeCLI - CLI サブプロセス実行、定数定義 |

## Child Spec Classification Criteria

以下の条件に該当する子仕様は `002-core` の子として作成する:

- pydantic-ai の `Model.request()` の挙動、または `stream_messages()` のストリーミング動作に影響するか?
- `ModelSettings` / `ModelProfile` に新しいフィールドを追加するか?
- `ClaudeCodeModel` のコンストラクタパラメータに影響するか?
- `CLIResponse` / `CLIUsage` のフィールドに変更が必要か?
- 例外階層に新しい例外クラスを追加するか?
- `ClaudeCodeCLI` のコマンド構築・実行フローに変更が必要か?
