# Feature Specification: IPC Bridge

**Feature Branch**: `006-ipc-bridge`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Child Spec (Feature)
**Parent Spec**: 004-tools
**Input**: User description: "set_agent_toolsets() で登録したツールを CLI バージョンに依存せず利用可能にする IPC ブリッジ機構"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - ツールセットの CLI 経由実行 (Priority: P1)

開発者は `set_agent_toolsets()` で登録した pydantic-ai ツールを、Claude Code CLI から呼び出せるようにする。現状 CLI は `type: "sdk"` の MCP サーバーを認識しないため、登録したツールが無視される。IPC ブリッジにより、CLI バージョンに依存せずツール呼び出しが可能になる。

**Why this priority**: ツール連携は Issue #110 で報告された根本的な機能不全であり、`set_agent_toolsets()` の存在意義に直結する。この問題が解決しない限り、ツール連携機能は事実上利用不可能。

**Independent Test**: pydantic-ai ツールを登録し、`model.request()` を実行して、CLI がツールを認識し呼び出し結果がモデルに返されることを確認する。

**Acceptance Scenarios**:

1. **Given** `set_agent_toolsets()` でツールを登録済みのモデル, **When** `model.request()` を実行する, **Then** CLI が登録されたツールを認識しツール一覧に含める
2. **Given** CLI がモデル応答内でツール呼び出しを要求した場合, **When** ツール呼び出しが実行される, **Then** 親プロセスのツール関数が実行され結果が MCP レスポンス形式で CLI に返される
3. **Given** ツール関数が親プロセスの依存関係や member agents にアクセスする場合, **When** ツールが実行される, **Then** ツール関数が元々アクセスするコンテキストが保持された状態で親プロセス内で実行される

---

### User Story 2 - IPC サーバーのライフサイクル管理 (Priority: P1)

開発者は IPC サーバーのライフサイクルを意識する必要がない。`model.request()` / `model.request_stream()` / `model.request_with_metadata()` の各呼び出し時に自動的にサーバーが起動し、完了時に自動的にクリーンアップされる。ソケットファイルのリーク等のリソース問題が発生しない。

**Why this priority**: リソースリークはプロダクション環境で致命的。IPC サーバーが正しく管理されなければ、ツール呼び出しの信頼性が損なわれる。

**Independent Test**: `model.request()` / `model.request_with_metadata()` を複数回呼び出し、各呼び出しの前後でソケットファイルが適切に作成・削除されることを確認する。

**Acceptance Scenarios**:

1. **Given** IPC ブリッジが構成されたモデル, **When** `model.request()` / `model.request_stream()` / `model.request_with_metadata()` のいずれかが呼ばれる, **Then** リクエスト開始時にサーバーが起動し、リクエスト完了時にサーバーが停止しソケットファイルが削除される
2. **Given** リクエスト処理中に例外が発生した場合, **When** 例外が伝播する, **Then** IPC サーバーはクリーンアップされソケットファイルは削除される
3. **Given** 前回のリクエストで異常終了し stale なソケットファイルが残っている場合, **When** 新しいリクエストが開始される, **Then** stale ファイルが検出・除去され新しいサーバーが正常に起動する

---

### User Story 3 - トランスポート方式の選択 (Priority: P2)

開発者は `set_agent_toolsets()` の `transport` パラメータで、ツール通信のトランスポート方式を選択できる。CLI が将来 `type: "sdk"` をサポートした場合に、コード変更なしで従来方式に切り替え可能である。

**Why this priority**: 将来の CLI アップデートに対する前方互換性の確保。当面の機能動作には必須ではないが、API 設計の一部として初期から組み込む。

**Independent Test**: `transport="stdio"` と `transport="sdk"` をそれぞれ指定し、対応する MCP サーバー設定が生成されることを確認する。

**Acceptance Scenarios**:

1. **Given** `transport="stdio"` を指定した場合, **When** `set_agent_toolsets()` を呼ぶ, **Then** IPC ブリッジ方式の MCP サーバー設定が生成される
2. **Given** `transport="sdk"` を指定した場合, **When** `set_agent_toolsets()` を呼ぶ, **Then** 従来の SDK 方式の MCP サーバー設定が生成される
3. **Given** `transport="auto"`（デフォルト）を指定した場合, **When** `set_agent_toolsets()` を呼ぶ, **Then** `"stdio"` と同等の動作をする（将来 CLI が `type: "sdk"` をサポートした時点でデフォルト動作を `"sdk"` に切り替え可能）

---

### User Story 4 - ブリッジプロセスの中継動作 (Priority: P1)

CLI が subprocess として起動するブリッジプロセスは、MCP プロトコル（JSON-RPC 2.0 over stdin/stdout）と IPC プロトコル（Unix socket）の間を中継する。CLI から見ると通常の stdio MCP サーバーとして振る舞う。

**Why this priority**: ブリッジプロセスは IPC アーキテクチャの中核であり、CLI ↔ 親プロセス間の通信が全てこのコンポーネントを経由する。

**Independent Test**: ブリッジプロセスを起動し、MCP `tools/list` と `tools/call` のリクエストを stdin で送信して、正しいレスポンスが stdout に返されることを確認する。

**Acceptance Scenarios**:

1. **Given** ブリッジプロセスが起動している状態, **When** MCP `tools/list` リクエストが送信される, **Then** 登録済みツールの一覧が MCP レスポンス形式で返される
2. **Given** ブリッジプロセスが起動している状態, **When** MCP `tools/call` リクエストが送信される, **Then** 親プロセスのツール関数が実行され結果が MCP レスポンスとして返される
3. **Given** ツール実行中に親プロセスでエラーが発生した場合, **When** エラーレスポンスが IPC 経由で返される, **Then** MCP エラーレスポンスとして CLI に伝播される

---

### Edge Cases

- ブリッジプロセスが親プロセスの IPC サーバーに接続できない場合、MCP エラーレスポンスとして CLI に報告される
- ツール関数実行中に例外が発生した場合、例外情報を含むエラーレスポンスが返される（例外がサイレントに握り潰されることはない）
- 親プロセスが異常終了した場合、ソケットファイルが一時ディレクトリに残る。次回の `start()` 呼び出しで stale ファイルを検出・削除する
- コマンドライン引数で渡すツールスキーマ JSON のサイズが OS のコマンドライン長制限を超える場合、明示的なエラーとして報告される
- `set_agent_toolsets()` を複数回呼び出した場合、以前の IPC サーバー構成が上書きされる（既存動作と一貫）
- ブリッジプロセスのソケット接続は `tools/call` 時に初めて確立される（lazy connect）。`tools/list` は起動時に受け取ったツールスキーマから応答するため IPC 不要。スキーマの受け渡し方式（コマンドライン引数、環境変数、一時ファイル等）は plan フェーズで決定する
- CLI が複数のツール呼び出しを並行で発行する場合、IPC 層で直列化される。CLI の通常動作ではツール呼び出しは逐次実行されるため、初期実装としての直列化は許容範囲と判断する。将来のリクエスト ID ベースの多重化は初期スコープ外
- ソケットファイルのパーミッションは owner only に設定され、他ユーザーからのアクセスを防止する
- ブリッジプロセスは親プロセスと同じ Python 実行環境で起動されるが、仮想環境の不整合等により MCP ライブラリが import できない場合、明示的なエラーとして報告される
- `set_agent_toolsets()` を複数回呼び出した際、前回の IPC サーバーの停止は非同期処理である。`set_agent_toolsets()` は同期メソッドであるため、前回の IPC サーバーの停止は次回のリクエスト開始時に遅延実行される
- リクエスト時のツールフィルタリングにより登録済みツールの一部のみが使用される場合、ブリッジプロセスが保持するツールスキーマと親プロセスが実行可能なツールに不整合が生じる可能性がある。フィルタリング発生時は IPC サーバーとブリッジを再構築して整合性を保証する

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは `set_agent_toolsets()` で登録したツールを、CLI が認識する MCP サーバー形式として提供しなければならない
- **FR-002**: システムは親プロセスとブリッジプロセス間で IPC 通信を確立し、ツール一覧の取得（`list_tools`）とツール実行（`call_tool`）をサポートしなければならない
- **FR-003**: ブリッジプロセスは MCP プロトコル（JSON-RPC 2.0 over stdin/stdout）に準拠し、CLI から見て標準的な stdio MCP サーバーとして動作しなければならない
- **FR-004**: システムは IPC サーバーのライフサイクル（起動・停止・クリーンアップ）を `model.request()` / `model.request_stream()` / `model.request_with_metadata()` のライフサイクルに統合しなければならない
- **FR-005**: システムは `transport` パラメータにより、IPC ブリッジ方式（`"stdio"`）と従来の SDK 方式（`"sdk"`）を切り替え可能でなければならない。`"auto"` は現時点では `"stdio"` と同等に動作する（CLI バージョン検出等の動的判定は行わない）
- **FR-006**: システムは IPC 通信のメッセージに最大サイズ制限を設けなければならない。制限を超過した場合は明示的なエラーとして報告される（分割送信は行わない）。具体的な制限値は plan フェーズで決定する
- **FR-007**: ツール関数は親プロセス内で実行されなければならない。ツール関数が元々アクセスするコンテキスト（依存関係、member agents 等）は保持される。ただし `RunContext` の全機能（retry カウンタ、累積 usage 等の Agent ループ固有の状態）の再現は要求しない
- **FR-008**: ツール実行中のエラーは IPC エラーレスポンスとして呼び出し元に伝播し、サイレントに無視されてはならない
- **FR-009**: ソケットファイルは owner only のパーミッションで作成され、パス名にはランダム要素を含めて衝突を回避しなければならない
- **FR-010**: システムは stale なソケットファイル（前回の異常終了で残留したもの）を検出・除去した上で新しいサーバーを起動しなければならない
- **FR-011**: `set_agent_toolsets()` の公開 API シグネチャに破壊的変更を加えてはならない（`transport` パラメータはキーワード引数として追加）
- **FR-012**: リクエスト時のツールフィルタリング（`_process_function_tools()` 相当）により MCP サーバーが再構築される場合、IPC サーバーとブリッジプロセスも整合性を保って再構築されなければならない。フィルタリングは同期メソッドから発生するが、IPC サーバーの停止は非同期であるため、この非同期ギャップを安全に処理しなければならない
- **FR-013**: ブリッジプロセスが使用する MCP サーバーライブラリは、プロジェクトの明示的な依存関係として宣言されなければならない（推移的依存への暗黙的な依存は禁止）

### Key Entities

- **IPC サーバー**: 親プロセス側で動作するサーバー。ツール定義を保持し、ブリッジプロセスからのリクエストに応じてツール関数を実行する
- **ブリッジプロセス**: CLI が subprocess として起動する MCP サーバー。MCP プロトコル（stdin/stdout）と IPC プロトコル間の中継を行う
- **IPC メッセージ**: 親プロセスとブリッジプロセス間で交換されるメッセージ。`list_tools`（ツール一覧取得）と `call_tool`（ツール実行）の2種類
- **ツール定義**: ツールの名前・説明・入力スキーマ・実行関数を含む構造。IPC サーバーがツールハンドラマップとして保持する
- **トランスポート設定**: `set_agent_toolsets()` の `transport` パラメータ。`"auto"`, `"stdio"`, `"sdk"` の3値を取り、ツール通信方式を決定する

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `set_agent_toolsets()` で登録したツールが CLI のツール一覧に表示され、モデルから呼び出し可能である
- **SC-002**: ツール呼び出し結果が親プロセスのコンテキストで実行され、正しい結果がモデルに返される
- **SC-003**: IPC サーバーが `model.request()` のライフサイクルに統合され、ソケットファイルのリークが発生しない
- **SC-004**: ツール実行中のエラーがサイレントに無視されず、エラーレスポンスとして伝播する
- **SC-005**: `transport` パラメータにより `"stdio"` と `"sdk"` の方式切り替えが可能である
- **SC-006**: stale なソケットファイルが自動検出・除去され、連続するリクエストが失敗しない
- **SC-007**: ソケットファイルのパーミッションが適切に設定され、他ユーザーからのアクセスが防止される
- **SC-008**: 全てのパブリック関数・メソッドに型注釈が付与されている
- **SC-009**: 公開 API `set_agent_toolsets()` のシグネチャに破壊的変更がない（既存のコードがそのまま動作する）
- **SC-010**: IPC ラウンドトリップ（ツール呼び出しリクエスト送信〜レスポンス受信）のオーバーヘッドが 10ms 以内である（ツール関数自体の実行時間を除く）
- **SC-011**: ブリッジプロセスの起動（MCP `tools/list` に応答可能になるまで）が 500ms 以内に完了する

## Scope

### In Scope

- IPC サーバー（親プロセス側サーバー）の実装
- ブリッジプロセス（stdio MCP サーバー ↔ IPC クライアント中継）の実装
- `set_agent_toolsets()` への `transport` パラメータ追加と IPC ブリッジ方式の統合
- `model.request()` / `model.request_stream()` / `model.request_with_metadata()` での IPC サーバーライフサイクル管理
- リクエスト時のツールフィルタリングに伴う IPC サーバー・ブリッジの再構築
- IPC 通信プロトコル
- ソケットファイルのセキュリティ（パーミッション、パス名のランダム化）

### Out of Scope

- `McpSdkServerConfig`（`type: "sdk"`）の CLI サポート追加（CLI 側の問題）
- CLI 側の MCP サーバー起動・管理ロジック（CLI 内部実装）
- pydantic-ai ツールの MCP サーバー変換ロジック自体（004-tools の既存スコープ）
- リクエスト ID ベースの並行ツール呼び出し多重化（将来の最適化）
- HTTP/SSE ベースの MCP トランスポート（ただし `transport` パラメータの `Literal` 型は将来の値追加に対応可能な設計とする）

## Assumptions

- CLI は stdio 方式の MCP サーバー設定を正しく処理し、指定されたコマンドを subprocess として起動する
- `mcp` ライブラリ（サーバー機能）は `pyproject.toml` に明示的な依存として追加される（FR-013）。確認済み: `claude-agent-sdk` は `mcp>=0.1.0` を依存に持ち、現在 `mcp 1.26.0` がインストール済み。`mcp.server` は import 可能
- Unix domain socket は対象プラットフォーム（Linux, macOS）で利用可能である
- ツール実行時間は IPC レイテンシに比べて十分長く、IPC オーバーヘッドは無視できる

## Dependencies

- **004-tools**: 親仕様。既存ツール変換パイプラインを再利用する
- **002-core**: `model.py` の `request()` / `request_stream()` ライフサイクルに IPC サーバー管理を統合する
