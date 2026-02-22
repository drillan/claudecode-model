# Feature Specification: SDK Bridge

**Feature Branch**: `003-sdk`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Parent Spec (Category)
**Parent Spec**: 001-architecture
**Input**: User description: "現在の実装から SDK Bridge のカテゴリ仕様を定義"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SDK レスポンスの CLIResponse 変換 (Priority: P1)

開発者は Claude Agent SDK の `query()` から返されるメッセージ列（`AssistantMessage`, `ResultMessage` 等）を、プロジェクト内部の統一データモデル `CLIResponse` に変換する。この変換により、SDK の型システムから pydantic-ai の型システムへの橋渡しが行われる。

**Why this priority**: レスポンス変換は ClaudeCodeModel の `request()` と `request_with_metadata()` の両方で必須の処理であり、この変換なしにはユーザーにレスポンスを返せない。SDK Bridge の根幹機能。

**Independent Test**: SDK の `ResultMessage` と `AssistantMessage` のモックオブジェクトを `convert_sdk_messages_to_cli_response()` に渡し、正しい `CLIResponse` が生成されることを確認する。

**Acceptance Scenarios**:

1. **Given** `ResultMessage` と `AssistantMessage` を含むメッセージ列, **When** `convert_sdk_messages_to_cli_response()` を呼び出す, **Then** `CLIResponse` が生成され、テキスト・メタデータ・使用量情報が正しく格納される
2. **Given** 複数の `ResultMessage` を含むメッセージ列, **When** 変換を実行する, **Then** 最後の `ResultMessage` がメタデータ抽出に使用される
3. **Given** `ResultMessage.result` が `None` の場合, **When** 変換を実行する, **Then** `AssistantMessage` の `TextBlock` からテキストが結合される
4. **Given** `ResultMessage.structured_output` が `dict` 型の場合, **When** 変換を実行する, **Then** `CLIResponse.structured_output` に格納される

---

### User Story 2 - トークン使用量データの変換 (Priority: P1)

開発者は SDK の usage データ（`dict[str, JsonValue]` 形式）を型安全な `CLIUsage` モデルに変換する。入力トークン、出力トークン、キャッシュ関連トークン、サーバーツール使用量、サービスティアの全てが保全される。

**Why this priority**: トークン使用量はコスト管理とモニタリングの基盤であり、レスポンス変換と同等に重要。`convert_usage_dict_to_cli_usage()` はレスポンス変換の内部で常に呼ばれる。

**Independent Test**: 様々な形式の usage dict（正常値、`None`、予期しない型）を `convert_usage_dict_to_cli_usage()` に渡し、正しい `CLIUsage` が生成されることを確認する。

**Acceptance Scenarios**:

1. **Given** 全フィールドが正常な整数値を持つ usage dict, **When** `convert_usage_dict_to_cli_usage()` を呼び出す, **Then** 全フィールドが正しく `CLIUsage` に変換される
2. **Given** `server_tool_use` ネストデータを含む usage dict, **When** 変換を実行する, **Then** `ServerToolUse` オブジェクトが生成され `web_search_requests` と `web_fetch_requests` が格納される
3. **Given** `cache_creation` ネストデータを含む usage dict, **When** 変換を実行する, **Then** `CacheCreation` オブジェクトが生成され `ephemeral_1h_input_tokens` と `ephemeral_5m_input_tokens` が格納される
4. **Given** usage が `None` の場合, **When** 変換を実行する, **Then** 全フィールドが 0 の `CLIUsage` が返される

---

### User Story 3 - SDK 互換パッチによる未知メッセージ型の処理 (Priority: P2)

開発者は SDK が未知のメッセージ型（例: `rate_limit_event`）を返した場合でも、クエリ全体が失敗せずに後続のメッセージ（`ResultMessage` を含む）を受信し続けられる。互換パッチがモジュールインポート時に適用され、未知の型のみをスキップし、他の全てのパースエラーは伝播する。

**Why this priority**: SDK の進化に伴い新しいメッセージ型が追加される可能性がある。未知の型でクエリ全体が失敗すると、ユーザーは結果を取得できない。ただし、レスポンス変換が正しく動作する前提条件であり P2。

**Independent Test**: 未知のメッセージ型を含む raw データを `_safe_parse_message()` に渡し、`None` が返され警告ログが出力されること、また構造不正のデータでは `MessageParseError` が送出されることを確認する。

**Acceptance Scenarios**:

1. **Given** 未知の `type` フィールドを持つメッセージデータ, **When** パッチ済み `parse_message()` が呼ばれる, **Then** `None` が返され警告ログに型名とデータが記録される
2. **Given** 既知の `type` だがフィールド不足のメッセージデータ, **When** パッチ済み `parse_message()` が呼ばれる, **Then** `MessageParseError` がそのまま送出される
3. **Given** パッチがモジュールインポート時に適用されている, **When** 複数の同時 SDK クエリが実行される, **Then** 全てのクエリで一貫してパッチが適用される

---

### User Story 4 - AssistantMessage からのテキスト抽出 (Priority: P2)

開発者は `AssistantMessage` の `content` ブロック列から `TextBlock` のテキストのみを抽出する。`ThinkingBlock` や `ToolUseBlock` は無視され、テキストのみが改行で結合される。

**Why this priority**: テキスト抽出は `ResultMessage.result` が `None` の場合の代替テキスト取得手段であり、レスポンス変換の補助機能。

**Independent Test**: `TextBlock`、`ThinkingBlock`、`ToolUseBlock` を混在させた `AssistantMessage` を `extract_text_from_assistant_message()` に渡し、`TextBlock` のテキストのみが返されることを確認する。

**Acceptance Scenarios**:

1. **Given** `TextBlock` のみを含む `AssistantMessage`, **When** `extract_text_from_assistant_message()` を呼び出す, **Then** 全テキストが改行で結合されて返される
2. **Given** `TextBlock` と `ThinkingBlock` と `ToolUseBlock` が混在する `AssistantMessage`, **When** 抽出を実行する, **Then** `TextBlock` のテキストのみが返される
3. **Given** `TextBlock` を含まない `AssistantMessage`, **When** 抽出を実行する, **Then** 空文字列が返される

---

### Edge Cases

- usage dict のフィールドが予期しない型（文字列、bool、リスト等）の場合、`_safe_int()` が警告ログを出力しデフォルト値 0 を使用する。これは型変換の堅牢性を保つための明示的な設計判断であり、`bool` は `int` のサブクラスとして `1`/`0` に変換される
- メッセージ列が空の場合、`convert_sdk_messages_to_cli_response()` は `ValueError` を送出する
- メッセージ列に `ResultMessage` が含まれない場合、`ValueError` を送出する
- SDK の `MessageParseError` のメッセージ文言が変更された場合（`"Unknown message type: "` プレフィックスが一致しない場合）、パッチは安全側に倒れ例外を再送出する（サイレント破損ではなく安全な失敗）
- `structured_output` が `dict` 以外の型の場合（例: `list`, `str`）、`None` として扱われる

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは SDK の `ResultMessage` を `CLIResponse` に変換しなければならない。`result`, `subtype`, `is_error`, `duration_ms`, `duration_api_ms`, `num_turns`, `session_id`, `total_cost_usd`, `usage`, `structured_output` の全フィールドを保全する
- **FR-002**: システムは SDK の usage データを型安全な `CLIUsage` モデルに変換しなければならない。基本トークン数（入力・出力・キャッシュ作成・キャッシュ読取）、サーバーツール使用量、サービスティア、キャッシュ作成情報を含む
- **FR-003**: システムは `AssistantMessage` の `content` ブロック列から `TextBlock` のテキストのみを抽出しなければならない。`ThinkingBlock` と `ToolUseBlock` は無視する
- **FR-004**: システムは SDK の `AssistantMessage` 列と `ResultMessage` の両方を含むメッセージ列を `CLIResponse` に変換する統合関数を提供しなければならない
- **FR-005**: システムは SDK の `parse_message` が未知のメッセージ型で `MessageParseError` を送出した場合、その例外をキャッチし `None` を返し警告ログを出力しなければならない
- **FR-006**: システムは未知メッセージ型以外の `MessageParseError`（フィールド不足、データ不正等）をそのまま再送出しなければならない
- **FR-007**: システムは SDK 互換パッチをアプリケーション起動時に一度だけ適用しなければならない。並行実行時にもパッチが一貫して適用されることを保証する
- **FR-008**: システムは usage dict のフィールドが予期しない型の場合、警告ログを出力し安全な型変換を行わなければならない（`_safe_int` 関数）
- **FR-009**: システムはレスポンス変換関数（`convert_sdk_messages_to_cli_response`, `convert_usage_dict_to_cli_usage`, `extract_text_from_assistant_message`）をパブリック API として公開しなければならない

### Key Entities

- **`convert_sdk_messages_to_cli_response()`**: SDK メッセージ列を `CLIResponse` に変換するエントリポイント関数。`AssistantMessage` からのテキスト抽出と `ResultMessage` からのメタデータ抽出を統合する
- **`convert_usage_dict_to_cli_usage()`**: SDK の usage dict を `CLIUsage` モデルに変換する関数。ネストされた `ServerToolUse` と `CacheCreation` の変換を含む
- **`extract_text_from_assistant_message()`**: `AssistantMessage` から `TextBlock` テキストのみを抽出する関数

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: SDK の `ResultMessage` と `AssistantMessage` を含むメッセージ列が正しい `CLIResponse` に変換される
- **SC-002**: usage dict の全フィールド（基本トークン、`server_tool_use`、`cache_creation`、`service_tier`）が `CLIUsage` に保全される
- **SC-003**: 未知の SDK メッセージ型がクエリ全体を失敗させず、後続のメッセージが正常に処理される
- **SC-004**: 未知メッセージ型以外のパースエラーは例外としてそのまま伝播する
- **SC-005**: 予期しない型入力に対して安全な型変換が行われ、警告ログが出力される
- **SC-006**: レスポンス変換関数がパブリック API として公開されている
- **SC-007**: 全てのパブリック関数・メソッドに型注釈が付与されている

## Scope

### In Scope (003-sdk)

- SDK の `ResultMessage` → `CLIResponse` 変換ロジック（`response_converter.py`）
- SDK の usage dict → `CLIUsage` 変換ロジック
- `AssistantMessage` からの `TextBlock` テキスト抽出
- `_safe_int()` による堅牢な型変換
- SDK 互換パッチ（`_sdk_compat.py`）: 未知メッセージ型のスキップ
- パブリック API としてのレスポンス変換関数のエクスポート

### Out of Scope (他カテゴリ)

- `ClaudeCodeModel` の `request()` / `stream_messages()` メソッド（→ 002-core）
- `_result_message_to_cli_response()` の `ClaudeCodeModel` 内実装（→ 002-core。`response_converter.py` と異なりインラインで変換）
- `_build_agent_options()` による `ClaudeAgentOptions` 構築（→ 002-core）
- `CLIResponse`, `CLIUsage` 等の型定義自体（→ 002-core）
- MCP サーバー変換・ツール変換（→ 004-tools）
- エラーメッセージ・ログフォーマット・テストインフラ（→ 005-dx）

## Design Principles

1. **型ブリッジとしての責務**: SDK の動的型（`dict[str, Any]`）からプロジェクトの型安全なモデル（`CLIUsage`, `CLIResponse`）への変換に特化する
2. **堅牢な型変換**: SDK から返される値が予期しない型であっても、明示的な警告ログとともに安全に変換する。サイレントな型エラーは禁止
3. **安全な失敗**: SDK のバージョン変更（新メッセージ型の追加、エラーメッセージ文言の変更等）に対して安全側に倒れる設計。パッチが適用できない場合は例外を伝播させる
4. **一時的パッチの明示性**: `_sdk_compat.py` は一時的なワークアラウンドであり、upstream の Issue 番号と削除条件をドキュメントで明示する
5. **副作用インポートの制限**: モジュールレベルの副作用（パッチ適用）は `_sdk_compat.py` のみに限定し、他のモジュールは純粋な関数として実装する

## Related Modules

| Module | Role |
|--------|------|
| `response_converter.py` | SDK メッセージ → CLIResponse 変換の中核モジュール |
| `_sdk_compat.py` | SDK 互換パッチ（未知メッセージ型対応） |

## Child Spec Classification Criteria

以下の条件に該当する子仕様は `003-sdk` の子として作成する:

- Claude Agent SDK の `query()` 呼び出し方法やオプション構築に影響するか?
- SDK のメッセージ型（`AssistantMessage`, `ResultMessage` 等）の処理に変更が必要か?
- SDK のレスポンスデータ（usage, structured_output 等）の変換ロジックに変更が必要か?
- SDK のバージョンアップに伴う互換性対応（新メッセージ型、API 変更等）か?
- `response_converter.py` または `_sdk_compat.py` の修正が必要か?
