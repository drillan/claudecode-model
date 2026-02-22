# Feature Specification: Tool & MCP System

**Feature Branch**: `004-tools`
**Created**: 2026-02-22
**Status**: Draft
**Type**: Parent Spec (Category)
**Parent Spec**: 001-architecture
**Input**: User description: "現在の実装から Tool & MCP System のカテゴリ仕様を定義"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - pydantic-ai Agent ツールの MCP サーバー変換 (Priority: P1)

開発者は `ClaudeCodeModel.set_agent_toolsets()` を使用して、pydantic-ai Agent に登録されたツール（`@agent.tool_plain` / `@agent.tool`）を Claude Agent SDK が認識する MCP サーバー形式に変換する。変換されたツールは `ClaudeAgentOptions.mcp_servers` に渡され、Claude がツール呼び出しを行える状態になる。

**Why this priority**: ツール連携はエージェントアプリケーションの根幹機能。pydantic-ai のツールエコシステムと Claude Agent SDK を橋渡しする唯一の手段であり、この機能なしにはツール使用が不可能。

**Independent Test**: pydantic-ai Agent にツールを登録し、`set_agent_toolsets(agent._function_toolset)` を呼び出して `McpSdkServerConfig` が生成されることを確認する。

**Acceptance Scenarios**:

1. **Given** `@agent.tool_plain` で定義されたツールを持つ Agent, **When** `set_agent_toolsets(agent._function_toolset)` を呼び出す, **Then** ツールが `SdkMcpTool` に変換され `McpSdkServerConfig` が生成される
2. **Given** 複数ツールを持つ `AgentToolset`, **When** `create_mcp_server_from_tools()` を呼び出す, **Then** 全ツールが `mcp__pydantic_tools__<tool_name>` 形式で公開される
3. **Given** ツール実行時に Claude がツールを呼び出した場合, **When** ツールラッパーが呼ばれる, **Then** 元のツール関数が実行され結果が MCP レスポンス形式（`{content: [{type: "text", text: ...}]}`）で返される
4. **Given** ツール実行中に例外が発生した場合, **When** ラッパーがエラーをキャッチする, **Then** 例外がログ記録された後に再送出される（`mcp_integration.py`）またはエラーレスポンス（`isError: true`）として返される（`tool_converter.py`）

---

### User Story 2 - pydantic-ai Tool オブジェクトの直接変換 (Priority: P1)

開発者は `convert_tool()` を使用して、pydantic-ai の `Tool` オブジェクトを個別に `SdkMcpTool` に変換する。`tool_converter.py` はツールの内部構造（`tool_def.name`, `tool_def.description`, `tool_def.parameters_json_schema`）にアクセスし、SDK 互換形式に変換する。

**Why this priority**: 低レベル変換 API は `mcp_integration.py` の基盤であり、カスタムツール変換パイプラインの構築にも使用される。パブリック API としてエクスポートされている。

**Independent Test**: pydantic-ai の `Tool` オブジェクトを `convert_tool()` に渡し、`SdkMcpTool` が正しい名前・説明・スキーマを持つことを確認する。

**Acceptance Scenarios**:

1. **Given** `tool_plain` で定義された `Tool` オブジェクト, **When** `convert_tool()` を呼び出す, **Then** `SdkMcpTool` が生成され `name`, `description`, `input_schema` が保持される
2. **Given** 同期関数で定義されたツール, **When** `_create_async_handler()` でラップされる, **Then** 非同期ハンドラーとして正しく動作する
3. **Given** `takes_ctx=True` のツールに `deps_context` なしで変換を試みる, **When** `_create_async_handler()` が呼ばれる, **Then** `NotImplementedError` が送出される
4. **Given** ツールの戻り値が辞書型の場合, **When** `_format_return_value_as_mcp()` が呼ばれる, **Then** JSON 文字列に変換された MCP レスポンスが返される
5. **Given** ツールの戻り値が既に MCP フォーマットの場合, **When** `_format_return_value_as_mcp()` が呼ばれる, **Then** そのまま `McpResponse` として返される

---

### User Story 3 - 依存関係付きツールの変換（実験的） (Priority: P2)

開発者は `convert_tool_with_deps()` を使用して、`RunContext` 経由で依存関係にアクセスするツールを変換する。依存関係はシリアライズ可能な型に限定され、`DepsContext` を通じてツール実行時に注入される。

**Why this priority**: 依存関係サポートはエージェントの高度なユースケース（API キー注入、設定オブジェクト参照等）に必要だが、基本的なツール変換が動作した後に対応可能。実験的 API として位置づけ。

**Independent Test**: `@agent.tool` で定義された `RunContext[Config]` 付きツールを `convert_tool_with_deps(tool, config)` で変換し、変換されたツールが `config` にアクセスできることを確認する。

**Acceptance Scenarios**:

1. **Given** `dataclass` の依存関係を持つツール, **When** `convert_tool_with_deps(tool, deps)` を呼び出す, **Then** `DepsContext` が作成されハンドラーに注入される
2. **Given** Pydantic `BaseModel` の依存関係を持つツール, **When** 変換を実行する, **Then** 正しく `DepsContext` が作成される
3. **Given** シリアライズ不可能な依存関係（例: `httpx.AsyncClient`）, **When** `convert_tool_with_deps()` を呼び出す, **Then** `UnsupportedDepsTypeError` が送出される

---

### User Story 4 - 依存関係のシリアライズ・デシリアライズ (Priority: P2)

開発者は `serialize_deps()` と `deserialize_deps()` を使用して、ツールの依存関係を JSON 文字列に変換・復元する。これにより、依存関係をプロセス間で受け渡すことが可能になる。

**Why this priority**: シリアライズ機能は依存関係サポートの基盤であり、`DepsContext` の動作に必須。ただし直接使用は限定的。

**Independent Test**: `dataclass` インスタンスを `serialize_deps()` で JSON に変換し、`deserialize_deps()` で復元して元のオブジェクトと等価であることを確認する。

**Acceptance Scenarios**:

1. **Given** `dataclass` インスタンス, **When** `serialize_deps()` を呼び出す, **Then** JSON 文字列が返される
2. **Given** Pydantic `BaseModel` インスタンス, **When** `serialize_deps()` を呼び出す, **Then** `model_dump_json()` の結果が返される
3. **Given** JSON 文字列と `dataclass` 型, **When** `deserialize_deps(json_str, type)` を呼び出す, **Then** `dacite.from_dict` で再構築されたインスタンスが返される
4. **Given** シリアライズ不可能なオブジェクト, **When** `serialize_deps()` を呼び出す, **Then** `UnsupportedDepsTypeError` が送出される

---

### User Story 5 - request() でのツール名マッチングとフィルタリング (Priority: P2)

開発者は `ClaudeCodeModel.request()` を呼び出す際、pydantic-ai が `ModelRequestParameters.function_tools` にツール名のリストを渡す。モデルは登録済みの toolsets からマッチするツールのみを含む MCP サーバーを再構築し、SDK に渡す。

**Why this priority**: ツールのフィルタリングは pydantic-ai のツール管理メカニズムとの統合に必須だが、基本的なツール登録・変換が動作した後に対応可能。

**Independent Test**: 3つのツールを登録後、`function_tools` に2つのツール名を指定して `_process_function_tools()` を呼び出し、指定されたツールのみを含む MCP サーバーが生成されることを確認する。

**Acceptance Scenarios**:

1. **Given** 登録済みの3つのツールと2つの `function_tools`, **When** `_process_function_tools()` が呼ばれる, **Then** 指定されたツールのみを含む MCP サーバーが生成される
2. **Given** `function_tools` に未登録のツール名が含まれている, **When** `_process_function_tools()` が呼ばれる, **Then** `ToolNotFoundError` が送出される
3. **Given** `function_tools` が提供されたが `set_agent_toolsets()` が呼ばれていない, **When** `_process_function_tools()` が呼ばれる, **Then** `ToolsetNotRegisteredError` が送出される

---

### Edge Cases

- ツール名が空文字列の場合、`ToolValidationError` が送出される
- ツールに `function` が登録されていない場合、`ToolValidationError` が送出される
- `_get_parameters_json_schema()` は3つのアクセスパターン（`parameters_json_schema`, `function_schema.json_schema`, `tool_def.parameters_json_schema`）を順に試行し、全て失敗すると `ToolValidationError` を送出する
- `parameters_json_schema` が `dict` 以外の型の場合、`ToolValidationError` が送出される
- `dataclass` のフィールドに前方参照（未解決の型）がある場合、`TypeHintResolutionError` が送出される
- `dataclass` の前方参照が文字列のまま解決できない場合、警告ログを出力し寛容に処理する（シリアライズ可能と仮定）
- ツール実行中に `asyncio.CancelledError` が発生した場合、キャンセルを伝播させタスクの適切なキャンセルを保証する
- `_format_return_value_as_mcp()` は `None` を空文字列に変換する
- `set_agent_toolsets()` を複数回呼び出すと、以前の toolsets が上書きされ警告ログが出力される

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは pydantic-ai の `AgentToolset`（`agent._function_toolset`）から `SdkMcpTool` のリストを抽出・変換しなければならない
- **FR-002**: システムは変換されたツールを `McpSdkServerConfig` としてパッケージし、`ClaudeAgentOptions.mcp_servers` に渡せる形式にしなければならない
- **FR-003**: システムは pydantic-ai の `Tool` オブジェクトを個別に `SdkMcpTool` に変換する低レベル API（`convert_tool()`）を提供しなければならない
- **FR-004**: システムはツールの JSON Schema を3つのアクセスパターン（`parameters_json_schema`, `function_schema.json_schema`, `tool_def.parameters_json_schema`）から抽出しなければならない
- **FR-005**: システムは同期・非同期両方のツール関数を非同期 MCP ハンドラーにラップしなければならない
- **FR-006**: システムはツール実行結果を MCP レスポンス形式（`{content: [{type: "text", text: ...}]}`）に変換しなければならない
- **FR-007**: システムはシリアライズ可能な依存関係（`dict`, `list`, プリミティブ型, `dataclass`, Pydantic `BaseModel`）付きツールの変換（`convert_tool_with_deps()`）をサポートしなければならない
- **FR-008**: システムは依存関係の JSON シリアライズ・デシリアライズ（`serialize_deps()`, `deserialize_deps()`）を提供しなければならない
- **FR-009**: システムは依存関係の型がシリアライズ不可能な場合に `UnsupportedDepsTypeError` を送出しなければならない
- **FR-010**: システムは `DepsContext` を通じて `RunContext` の軽量エミュレーションを提供し、ツール実行時に依存関係を注入しなければならない
- **FR-011**: システムは `_process_function_tools()` で pydantic-ai の `function_tools` リストからマッチするツールのみを含む MCP サーバーを動的に再構築しなければならない
- **FR-012**: システムはツール名のバリデーション（空文字列禁止）、関数存在チェック、JSON Schema 型チェックを行い、不正な場合は `ToolValidationError` を送出しなければならない
- **FR-013**: システムは `convert_tool()`, `convert_tool_with_deps()`, `convert_tools_to_mcp_server()`, `DepsContext` をパブリック API としてエクスポートしなければならない

### Key Entities

- **`PydanticAITool`**: pydantic-ai ツールインターフェースの Protocol。`name`, `description`, `parameters_json_schema`, `function` 属性を持つ
- **`AgentToolset`**: pydantic-ai Agent の内部ツールセット（`_AgentFunctionToolset`）に対する Protocol。`tools: dict[str, PydanticAITool]` を持つ
- **`ToolDefinition`**: ツール定義を格納する TypedDict。`name`, `description`, `input_schema`, `function` フィールドを持つ（`mcp_integration.py`）
- **`SdkMcpTool`**: Claude Agent SDK のツール表現。`name`, `description`, `input_schema`, `handler` を持つ
- **`McpSdkServerConfig`**: SDK の `create_sdk_mcp_server()` が返す MCP サーバー設定
- **`McpResponse`**: MCP レスポンス形式の TypedDict。`content: list[McpTextContent]` と `isError: bool` を持つ（`tool_converter.py`）
- **`DepsContext[T]`**: `RunContext` の軽量エミュレーション。`deps: T` プロパティで依存関係にアクセスする Generic クラス
- **`ToolValidationError`**: ツールバリデーション失敗時の例外（`ValueError` 派生）
- **`UnsupportedDepsTypeError`**: シリアライズ不可能な依存関係型の例外（`ClaudeCodeError` 派生）
- **`ToolsetNotRegisteredError`**: `set_agent_toolsets()` 未呼び出し時の例外（`ClaudeCodeError` 派生）
- **`ToolNotFoundError`**: 要求されたツールが登録されていない場合の例外（`ClaudeCodeError` 派生）
- **`TypeHintResolutionError`**: `dataclass` の型ヒント解決失敗時の例外（`ClaudeCodeError` 派生）

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: pydantic-ai Agent のツール（`@agent.tool_plain`）が `SdkMcpTool` に変換され、Claude がツールを呼び出せる
- **SC-002**: 変換されたツールの実行結果が MCP レスポンス形式で返され、Claude に処理される
- **SC-003**: シリアライズ可能な依存関係付きツール（`@agent.tool` + `RunContext`）が `convert_tool_with_deps()` で変換され、依存関係にアクセスできる
- **SC-004**: シリアライズ不可能な依存関係が `UnsupportedDepsTypeError` で明示的に拒否される
- **SC-005**: ツール名・関数・JSON Schema のバリデーションエラーが構造化例外として伝播する
- **SC-006**: `set_agent_toolsets()` 後に `function_tools` のフィルタリングが正しく動作し、マッチしないツールは `ToolNotFoundError` で報告される
- **SC-007**: `convert_tool()`, `convert_tool_with_deps()`, `convert_tools_to_mcp_server()`, `DepsContext` がパブリック API としてエクスポートされている
- **SC-008**: 全てのパブリック関数・メソッドに型注釈が付与されている
- **SC-009**: 依存関係の JSON シリアライズ→デシリアライズのラウンドトリップが `dataclass` と Pydantic `BaseModel` の両方で成功する

## Scope

### In Scope (004-tools)

- `mcp_integration.py`: pydantic-ai ツールセットから MCP サーバーへの変換パイプライン
- `tool_converter.py`: pydantic-ai `Tool` オブジェクトから `SdkMcpTool` への低レベル変換
- `deps_support.py`: シリアライズ可能な依存関係のバリデーション・シリアライズ・デシリアライズ・`DepsContext`
- `PydanticAITool` / `AgentToolset` Protocol の定義
- ツール実行結果の MCP レスポンス形式への変換
- `ClaudeCodeModel._process_function_tools()` でのツール名マッチング・フィルタリング
- ツールバリデーション（名前、関数、JSON Schema）
- ツール関連の例外階層（`ToolValidationError`, `UnsupportedDepsTypeError`, `ToolsetNotRegisteredError`, `ToolNotFoundError`, `TypeHintResolutionError`）

### Out of Scope (他カテゴリ)

- `ClaudeCodeModel.request()` の全体的な実行フロー（→ 002-core）
- `ClaudeAgentOptions` の構築ロジック（→ 002-core）
- SDK レスポンスの `CLIResponse` 変換（→ 003-sdk）
- 例外メッセージの UX・ログフォーマット（→ 005-dx）

## Design Principles

1. **Protocol ベースの抽象化**: pydantic-ai の内部型に直接依存せず、`PydanticAITool` / `AgentToolset` Protocol を通じてアクセスする。pydantic-ai の内部構造変更に対する耐性を確保する
2. **二層変換アーキテクチャ**: `mcp_integration.py`（高レベル：toolset → MCP サーバー）と `tool_converter.py`（低レベル：Tool → SdkMcpTool）の2層で責務を分離する
3. **明示的エラー伝播**: ツールバリデーション失敗は `ToolValidationError`、依存関係の型不正は `UnsupportedDepsTypeError` として構造化例外で伝播する。サイレントな無視や暗黙的な代入は禁止
4. **シリアライズ可能性の保証**: `DepsContext` は明示的なシリアライズ可能性チェックを強制する。非シリアライズ型（`httpx.AsyncClient`、DB 接続等）は即座に拒否する
5. **実験的 API の明示性**: `convert_tool_with_deps()` と `DepsContext` は実験的 API として明示的にマークされ、API 変更の可能性がドキュメントに記載される

## Related Modules

| Module | Role |
|--------|------|
| `mcp_integration.py` | pydantic-ai ツールセット → MCP サーバー変換の高レベル API |
| `tool_converter.py` | pydantic-ai Tool → SdkMcpTool の低レベル変換、依存関係付き変換 |
| `deps_support.py` | シリアライズ可能依存関係のバリデーション・シリアライズ・DepsContext |

## Child Spec Classification Criteria

以下の条件に該当する子仕様は `004-tools` の子として作成する:

- pydantic-ai のツールを MCP サーバーに変換する処理に変更が必要か?
- `AgentToolset` / `PydanticAITool` Protocol に新しい属性やメソッドを追加するか?
- `SdkMcpTool` の生成ロジック（名前解決、スキーマ変換、ハンドラーラッピング）に変更が必要か?
- 依存関係のシリアライズ/デシリアライズに影響するか?
- `DepsContext` の機能拡張（例: 新しい `RunContext` フィールドのエミュレーション）が必要か?
- ツールバリデーション（名前、関数、スキーマ）のルール変更か?
- `_process_function_tools()` のツール名マッチングロジックに変更が必要か?
