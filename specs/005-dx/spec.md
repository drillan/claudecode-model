# Feature Specification: Developer Experience

**Feature Branch**: `005-dx`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Parent Spec (Category)
**Parent Spec**: 001-architecture
**Input**: User description: "現在の実装から Developer Experience のカテゴリ仕様を定義"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 構造化エラーメッセージによるトラブルシューティング (Priority: P1)

開発者は claudecode-model の利用中にエラーが発生した場合、例外メッセージから問題の原因と解決方法を即座に把握する。全ての例外は `ClaudeCodeError` 派生の構造化例外として伝播し、解決ヒント（メッセージ本文）を含む。`CLIExecutionError` はさらにエラー種別（`error_type`）・復旧可能性（`recoverable`）を持つ。各例外は用途に応じた構造化属性（`raw_output`, `type_name`, `missing_tools`, `session_id` 等）を提供する。

**Why this priority**: エラーメッセージの品質は開発者体験の根幹。不明瞭なエラーはデバッグ時間を大幅に増加させ、ライブラリ採用の障壁になる。

**Independent Test**: `CLINotFoundError` を受け取った開発者が、メッセージ内のインストール URL を参照して問題を解決できることを確認する。

**Acceptance Scenarios**:

1. **Given** Claude CLI がインストールされていない環境, **When** `ClaudeCodeModel` を使用する, **Then** `CLINotFoundError` が送出され、メッセージにインストール URL が含まれる
2. **Given** CLI 実行がタイムアウトした場合, **When** `CLIExecutionError` が送出される, **Then** `error_type="timeout"`, `recoverable=True` が設定され、タイムアウト値の増加を提案するメッセージが含まれる
3. **Given** ツールが未登録の状態で `function_tools` が提供された場合, **When** `ToolsetNotRegisteredError` が送出される, **Then** `set_agent_toolsets()` の呼び出し方法がメッセージに含まれる
4. **Given** 要求されたツールが登録済みツールに存在しない場合, **When** `ToolNotFoundError` が送出される, **Then** 未登録ツール名と利用可能なツール名の両方がメッセージに含まれる
5. **Given** シリアライズ不可能な依存関係型が指定された場合, **When** `UnsupportedDepsTypeError` が送出される, **Then** サポートされる型の一覧がメッセージに含まれる
6. **Given** 構造化出力の抽出がリトライ上限に達した場合, **When** `StructuredOutputError` が送出される, **Then** `session_id` が含まれ、セッションファイルのパスが案内される
7. **Given** CLI 実行中にユーザーが Ctrl-C を押した場合, **When** `CLIInterruptedError` が送出される, **Then** サブプロセスが安全に終了されたことを示すメッセージが含まれる
8. **Given** CLI の JSON 出力がパース不能な場合, **When** `CLIResponseParseError` が送出される, **Then** `raw_output` 属性で生出力にアクセスでき、メッセージにパース失敗の詳細が含まれる
9. **Given** データクラスの型ヒントが解決不能な場合, **When** `TypeHintResolutionError` が送出される, **Then** 問題の型名（`type_name`）と元のエラー（`original_error`）がメッセージに含まれる

---

### User Story 2 - デバッグログによる実行トレース (Priority: P1)

開発者は `CLAUDECODE_MODEL_LOG_LEVEL=DEBUG` 環境変数を設定することで、SDK クエリの実行フロー・パラメータ・結果を詳細にトレースする。ログは各モジュール（model, cli, mcp_integration, response_converter, deps_support, tool_converter）に配置され、処理の開始・完了・異常を記録する。

**Why this priority**: デバッグログは問題調査の必須ツール。本番環境では WARNING レベルで抑制し、トラブルシューティング時のみ DEBUG で有効化するフロー制御が不可欠。

**Independent Test**: `CLAUDECODE_MODEL_LOG_LEVEL=DEBUG` を設定し、`ClaudeCodeModel` の初期化と `request()` 実行で、初期化パラメータ・SDK クエリパラメータ・結果（duration, num_turns, tokens）がログに出力されることを確認する。

**Acceptance Scenarios**:

1. **Given** `CLAUDECODE_MODEL_LOG_LEVEL=DEBUG` が設定されている, **When** `ClaudeCodeModel` を初期化する, **Then** 初期化パラメータ（model_name, working_directory, timeout, permission_mode, max_turns）がログに記録される
2. **Given** デバッグログが有効な状態, **When** `_execute_sdk_query()` が実行される, **Then** クエリの開始（prompt_length, timeout）と完了（duration_ms, num_turns, is_error, input_tokens, output_tokens）がログに記録される
3. **Given** `CLAUDECODE_MODEL_LOG_LEVEL` が未設定, **When** ライブラリをインポートする, **Then** ログレベルは WARNING となり、DEBUG/INFO ログは出力されない
4. **Given** `CLAUDECODE_MODEL_LOG_LEVEL` に無効な値が設定されている, **When** ライブラリをインポートする, **Then** `warnings.warn()` で警告が発行され、ログレベルは WARNING になる
5. **Given** 環境変数が明示的に設定されている, **When** ライブラリをインポートする, **Then** `StreamHandler` が1つだけ追加される（複数インポートで重複しない）

---

### User Story 3 - JSON 抽出ユーティリティによる堅牢な出力パース (Priority: P2)

開発者は `extract_json()` を使用して、Claude Code CLI の出力からJSON データを確実に抽出する。CLI 出力にはテキストとJSON が混在する場合があり、4段階の抽出ストラテジー（直接パース → コードブロック → オブジェクトパターン → 配列パターン）で堅牢に対応する。

**Why this priority**: 構造化出力の抽出は CLI サブプロセスモード（`ClaudeCodeCLI`）の信頼性に直結するが、SDK モード（`ClaudeCodeModel`）ではレスポンスが構造化されているため必須度は下がる。

**Independent Test**: JSON を含むテキストを `extract_json()` に渡し、正しくパースされた辞書が返されることを確認する。

**Acceptance Scenarios**:

1. **Given** 有効な JSON 文字列, **When** `extract_json()` に渡す, **Then** パースされた辞書が返される
2. **Given** `` ```json ... ``` `` コードブロックを含むテキスト, **When** `extract_json()` に渡す, **Then** コードブロック内の JSON が抽出される
3. **Given** テキストの中に `{...}` パターンが埋め込まれている, **When** `extract_json()` に渡す, **Then** ブラケットカウンティングで正しく JSON オブジェクトが抽出される
4. **Given** JSON を一切含まないテキスト, **When** `extract_json()` に渡す, **Then** `ValueError` が送出され、各ストラテジーの失敗理由がメッセージに含まれる

---

### User Story 4 - テスト基盤による品質保証 (Priority: P2)

開発者はユニットテストを通じて、各モジュールの動作を個別に検証する。1機能 = 1テストファイルの原則に従い、テストの発見性と保守性を確保する。共有テストヘルパー（`conftest.py`）により、テスト間のボイラープレートを削減する。

**Why this priority**: テスト基盤は品質保証の根幹だが、エンドユーザーが直接触れるインターフェースではないため P2。

**Independent Test**: `pytest` を実行し、全テストが通過することを確認する。

**Acceptance Scenarios**:

1. **Given** 1つの実装モジュール, **When** 対応するテストファイルを特定する, **Then** `test_<module_name>.py` が存在する
2. **Given** テストファイル群, **When** `conftest.py` を確認する, **Then** 共有ヘルパー（モックファクトリ等）が定義されている
3. **Given** 非同期関数を含むモジュール, **When** テストを実行する, **Then** `pytest-asyncio` の `asyncio_mode = "auto"` により特別なデコレータなしで非同期テストが実行される

---

### User Story 5 - パブリック API のエクスポートと型安全性 (Priority: P2)

開発者は `claudecode_model` パッケージの `__init__.py` から、全てのパブリッククラス・関数・型を `__all__` 経由でインポートする。IDE のオートコンプリートとドキュメント生成が正しく機能する。

**Why this priority**: API のエクスポート設計は開発者がライブラリを発見・利用する際の第一接触点だが、機能そのものではないため P2。

**Independent Test**: `from claudecode_model import ClaudeCodeModel, CLIExecutionError` が成功し、型チェッカー（mypy）がエラーを出さないことを確認する。

**Acceptance Scenarios**:

1. **Given** `claudecode_model` パッケージ, **When** `__all__` を確認する, **Then** 全パブリック API（クラス、関数、型、定数）が列挙されている
2. **Given** パブリック API の関数・メソッド, **When** 型注釈を確認する, **Then** 全てに型注釈が付与されており `Any` 型は使用されていない
3. **Given** `__init__.py`, **When** インポートする, **Then** ログ設定が自動的に適用され、副作用は `_sdk_compat` のパッチのみである

---

### User Story 6 - 品質チェックツールチェーン (Priority: P3)

開発者はコミット前に `ruff check --fix . && ruff format . && mypy .` を実行し、コードの一貫性と型安全性を保証する。ツールチェーンの設定は `pyproject.toml` で一元管理される。

**Why this priority**: 開発プロセスの効率化に寄与するが、ランタイムの機能には直接影響しない。

**Independent Test**: `ruff check . && mypy .` を実行し、エラーが0件であることを確認する。

**Acceptance Scenarios**:

1. **Given** プロジェクトのソースコード, **When** `ruff check .` を実行する, **Then** リンティングエラーが0件である
2. **Given** プロジェクトのソースコード, **When** `ruff format --check .` を実行する, **Then** フォーマット差分が0件である
3. **Given** プロジェクトのソースコード, **When** `mypy .` を実行する, **Then** 型エラーが0件である

---

### Edge Cases

- `CLAUDECODE_MODEL_LOG_LEVEL` が空文字列の場合、環境変数は「明示的に設定された」と判定され `StreamHandler` が追加される（ログレベルは WARNING）
- `extract_json()` に渡されたテキストが 200 文字を超える場合、`ValueError` のメッセージ内のプレビューが 200 文字で切り詰められる
- ネストされた JSON オブジェクト（`{...{...}...}`）の場合、ブラケットカウンティングにより最外のオブジェクトが正しく抽出される
- JSON 文字列内のエスケープされたブラケット（`"{\"key\":\"value\"}"`）が正しく処理される
- 同じモジュールの複数回インポート（`importlib.reload`）でもログハンドラーが重複しない

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは全てのエラーを `ClaudeCodeError` 派生の構造化例外で伝播し、各例外メッセージに問題の原因と解決方法を含めなければならない
- **FR-002**: システムは `CLAUDECODE_MODEL_LOG_LEVEL` 環境変数によるログレベル制御（DEBUG, INFO, WARNING, ERROR, CRITICAL）をサポートしなければならない
- **FR-003**: システムは環境変数未設定時に WARNING レベルをデフォルトとし、デバッグ/情報ログを抑制しなければならない
- **FR-004**: システムは無効なログレベル値に対して `warnings.warn()` で明確な警告を発行しなければならない
- **FR-005**: システムは `extract_json()` で4段階の抽出ストラテジー（直接パース、コードブロック、オブジェクトパターン、配列パターン）を提供し、失敗時に全ストラテジーの失敗理由を含むエラーを送出しなければならない
- **FR-006**: システムは1機能 = 1テストファイルの原則に従ったテスト構造を維持しなければならない
- **FR-007**: システムは全パブリック API を `__init__.py` の `__all__` 経由でエクスポートしなければならない
- **FR-008**: システムは全パブリック関数・メソッドに型注釈を付与しなければならず、`Any` 型を使用してはならない
- **FR-009**: システムは ruff（リンター/フォーマッター）と mypy（型チェッカー）による品質チェックをサポートし、設定を `pyproject.toml` で管理しなければならない
- **FR-010**: システムは `CLIExecutionError` に `error_type`（Literal 型）と `recoverable` フラグを含め、エラーのプログラマブルな分類を可能にしなければならない
- **FR-011**: システムは SDK の未知メッセージ型に対して警告ログを出力し、明示的にスキップしなければならない（`_sdk_compat.py`）

### Key Entities

- **`ClaudeCodeError`**: 全例外の基底クラス。ライブラリ固有のエラーを他の例外と区別するためのマーカー
- **`ErrorType`**: エラー種別の Literal 型（`"timeout"`, `"permission"`, `"cli_not_found"`, `"invalid_response"`, `"unknown"`）。プログラマブルなエラーハンドリングに使用
- **`extract_json()`**: CLI 出力テキストから JSON を抽出するユーティリティ。4段階のストラテジーで堅牢性を確保
- **ログ基盤**: `CLAUDECODE_MODEL_LOG_LEVEL` 環境変数と `logging.getLogger("claudecode_model")` による構造化ログシステム

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全ての構造化例外（9種）のメッセージに、問題の原因と解決方法（または調査手段）が含まれている
- **SC-002**: `CLAUDECODE_MODEL_LOG_LEVEL=DEBUG` で実行時に、各モジュールの主要処理（初期化、クエリ実行、ツール処理、レスポンス変換）がトレースできる
- **SC-003**: `extract_json()` が4段階の抽出ストラテジーを持ち、失敗時のエラーメッセージに全ストラテジーの失敗理由が含まれる
- **SC-004**: 全実装モジュールに対応するテストファイルが存在し、テストカバレッジが維持されている
- **SC-005**: `__all__` に列挙された全パブリック API が `from claudecode_model import <name>` でインポート可能である
- **SC-006**: `ruff check .`, `ruff format --check .`, `mypy .` の全てがエラー0件で通過する
- **SC-007**: 全パブリック関数・メソッドに型注釈が付与されており、`Any` 型が使用されていない
- **SC-008**: 無効なログレベル設定時に明確な警告メッセージが出力され、適切なログレベルにリカバリーされる

## Scope

### In Scope (005-dx)

- `exceptions.py`: 構造化例外階層（`ClaudeCodeError` 派生9クラス）とエラーメッセージの品質
- `__init__.py`: ログ基盤（`CLAUDECODE_MODEL_LOG_LEVEL`）、パブリック API エクスポート（`__all__`）
- `json_utils.py`: CLI 出力からの JSON 抽出ユーティリティ
- `_sdk_compat.py`: SDK 互換パッチの警告ログ設計
- 各モジュールの `logger.debug()` / `logger.warning()` / `logger.error()` 呼び出しの一貫性
- テスト基盤: テストファイル構造（1機能=1テスト）、共有ヘルパー（`conftest.py`）、pytest 設定
- 品質ツールチェーン: ruff・mypy の設定（`pyproject.toml`）

### Out of Scope (他カテゴリ)

- `ClaudeCodeModel.request()` の実行ロジック（→ 002-core）
- SDK レスポンスの `CLIResponse` 変換ロジック（→ 003-sdk）
- ツール変換・MCP サーバー生成ロジック（→ 004-tools）
- CI/CD パイプラインの構築（→ 子仕様として別途定義）
- CLI エントリーポイント（`main()`）の本実装（→ 子仕様として別途定義）

## Design Principles

1. **解決指向のエラーメッセージ**: 全例外メッセージは「何が起きたか」に加え「どう解決するか」を含む。開発者がスタックトレースだけで問題を解決できることを目指す
2. **段階的ログ開示**: デフォルトでは WARNING 以上のみ出力し、`CLAUDECODE_MODEL_LOG_LEVEL=DEBUG` で詳細トレースを有効化する。本番環境のノイズを抑制しつつ、トラブルシューティング時の情報量を確保する
3. **明示的エラー伝播**: サイレントなエラー抑制・暗黙的デフォルト値代入を禁止する。全てのエラーは構造化例外として伝播し、ログで明示的に記録される
4. **堅牢な出力パース**: CLI 出力のバリエーション（純粋 JSON、コードブロック、テキスト混在）に対して、複数の抽出ストラテジーで段階的に対応する。全ストラテジーの失敗を集約してエラーメッセージに含める
5. **型安全の徹底**: `Any` 型を禁止し、全パブリック API に型注釈を付与する。mypy による静的型チェックで型安全性を継続的に保証する

## Related Modules

| Module | Role |
|--------|------|
| `exceptions.py` | 構造化例外階層（`ClaudeCodeError` 派生9クラス）、エラー種別・復旧フラグ |
| `__init__.py` | ログ基盤（`CLAUDECODE_MODEL_LOG_LEVEL`）、パブリック API エクスポート |
| `json_utils.py` | CLI 出力からの JSON 抽出ユーティリティ（4段階ストラテジー） |
| `_sdk_compat.py` | SDK 互換パッチの警告ログ設計 |
| `pyproject.toml` | 品質ツール（ruff, mypy, pytest）の設定 |

## Child Spec Classification Criteria

以下の条件に該当する子仕様は `005-dx` の子として作成する:

- 開発者が直接触れるインターフェース（エラーメッセージ、ログ出力、CLI）の変更か?
- 例外メッセージの文言・構造・属性の追加・変更か?
- ログフォーマット・レベル・出力先の変更か?
- テスト基盤（conftest, pytest 設定、テストヘルパー）の改善か?
- 品質ツールチェーン（ruff, mypy）のルール追加・設定変更か?
- ドキュメント（README、API ドキュメント、使用例）の追加・更新か?
- CI/CD パイプライン（GitHub Actions 等）の構築・修正か?
- `__init__.py` のパブリック API エクスポート（`__all__`）の変更か?
- `json_utils.py` の抽出ストラテジーの追加・修正か?
