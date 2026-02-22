# Tasks: IPC Bridge

**Input**: Design documents from `/specs/006-ipc-bridge/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD 必須（Constitution Article 1）。各フェーズでテスト → Red 確認 → 実装 → Green の順で進行。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- Source: `src/claudecode_model/`
- Tests: `tests/`
- Config: `pyproject.toml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: パッケージ構造、依存関係、例外クラスの基盤を構築

- [ ] T001 Add `mcp>=1.0.0` to `[project.dependencies]` in `pyproject.toml` (FR-013)
- [ ] T002 [P] Create `src/claudecode_model/ipc/__init__.py` with `TransportType`, `DEFAULT_TRANSPORT` exports and package docstring
- [ ] T003 [P] Add IPC exception classes (`IPCError`, `IPCConnectionError`, `IPCMessageSizeError`, `IPCToolExecutionError`, `BridgeStartupError`) to `src/claudecode_model/exceptions.py`
- [ ] T004 [P] Add new IPC types and exceptions to public exports in `src/claudecode_model/__init__.py`

---

## Phase 2: Foundational - IPC Protocol (Blocking Prerequisites)

**Purpose**: IPC プロトコルの共有型とメッセージフレーミング。US4（ブリッジ）と US1（サーバー）の両方が依存。

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests

- [ ] T005 Write tests for IPC protocol module in `tests/test_ipc_protocol.py`: message TypedDict construction, length-prefix framing (send/receive round-trip), MAX_MESSAGE_SIZE exceeded error, empty message handling, invalid JSON handling

### Implementation

- [ ] T006 [P] Implement protocol constants (`MAX_MESSAGE_SIZE`, `LENGTH_PREFIX_SIZE`, `SOCKET_PERMISSIONS`, `SOCKET_FILE_PREFIX`, `SOCKET_FILE_SUFFIX`, `SCHEMA_FILE_PREFIX`) and message TypedDicts (`IPCRequest`, `CallToolParams`, `IPCResponse`, `ToolResult`, `ToolResultContent`, `IPCErrorResponse`, `IPCErrorPayload`) in `src/claudecode_model/ipc/protocol.py`
- [ ] T007 Implement length-prefixed message framing functions (`send_message`, `receive_message`) with `IPCMessageSizeError` validation in `src/claudecode_model/ipc/protocol.py`

**Checkpoint**: Protocol layer ready - `send_message`/`receive_message` で IPC メッセージの送受信が可能

---

## Phase 3: User Story 4 - ブリッジプロセスの中継動作 (Priority: P1)

**Goal**: CLI が subprocess として起動するブリッジプロセスが、MCP プロトコル (stdin/stdout) と IPC プロトコル (Unix socket) の間を中継する

**Independent Test**: ブリッジプロセスを起動し、MCP `tools/list` と `tools/call` のリクエストを stdin で送信して、正しいレスポンスが stdout に返されることを確認する

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T008 [US4] Write tests for bridge process in `tests/test_ipc_bridge.py`: schema file loading, MCP `tools/list` response from local schema, MCP `tools/call` relay via IPC, IPC connection failure → MCP error response, tool execution error propagation

### Implementation for User Story 4

- [ ] T009 [P] [US4] Implement schema file loading (JSON → `list[ToolSchema]`) and MCP `tools/list` handler using `mcp.server.Server.list_tools()` decorator in `src/claudecode_model/ipc/bridge.py`
- [ ] T010 [P] [US4] Implement IPC client with lazy connect (`asyncio.open_unix_connection`), persistent connection reuse, and `call_tool` request/response handling in `src/claudecode_model/ipc/bridge.py`
- [ ] T011 [US4] Assemble MCP stdio server with `mcp.server.stdio.stdio_server` and add `if __name__ == "__main__"` entry point (args: socket_path, schema_path) in `src/claudecode_model/ipc/bridge.py`

**Checkpoint**: `python -m claudecode_model.ipc.bridge <socket_path> <schema_path>` でブリッジプロセスが起動し、stdin/stdout で MCP リクエストに応答可能

---

## Phase 4: User Story 1 - ツールセットの CLI 経由実行 (Priority: P1) 🎯 MVP

**Goal**: `set_agent_toolsets()` で登録した pydantic-ai ツールが CLI から呼び出し可能になる

**Independent Test**: pydantic-ai ツールを登録し、`model.request()` を実行して、CLI がツールを認識し呼び出し結果がモデルに返されることを確認する

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T012 [US1] Write tests for IPC server in `tests/test_ipc_server.py`: Unix socket bind/accept, `call_tool` dispatch to registered handler, tool execution result returned as IPCResponse, tool execution error returned as IPCErrorResponse, unknown tool name → error
- [ ] T013 [US1] Write tests for IPC session and model integration in `tests/test_ipc_server.py`: IPCSession create/start/stop lifecycle, socket path generation with UUID, schema file creation with correct permissions (0o600)

### Implementation for User Story 1

- [ ] T014 [US1] Implement `IPCServer` class (asyncio Unix socket server, connection handler, tool handler dispatch via protocol `send_message`/`receive_message`) in `src/claudecode_model/ipc/server.py`
- [ ] T015 [US1] Implement `IPCSession` class (socket/schema path generation with UUID, schema file write with 0o600 permissions, tool handler map from `create_tool_wrapper()`, start/stop methods) in `src/claudecode_model/ipc/server.py`
- [ ] T016 [P] [US1] Add `create_stdio_mcp_config()` function that generates `McpStdioServerConfig` with `sys.executable -m claudecode_model.ipc.bridge` command in `src/claudecode_model/mcp_integration.py`
- [ ] T017 [US1] Widen `self._mcp_servers` type annotation to `dict[str, McpSdkServerConfig | McpStdioServerConfig]` and update `get_mcp_servers()` return type in `src/claudecode_model/model.py`
- [ ] T018 [US1] Integrate IPC into `set_agent_toolsets()`: create `IPCSession`, write schema file, store `McpStdioServerConfig` in `self._mcp_servers` in `src/claudecode_model/model.py`

**Checkpoint**: `set_agent_toolsets()` 呼び出しで McpStdioServerConfig が生成され、IPC サーバーがツール呼び出しを処理可能

---

## Phase 5: User Story 2 - IPC サーバーのライフサイクル管理 (Priority: P1)

**Goal**: IPC サーバーが `request()`/`stream_messages()`/`request_with_metadata()` のライフサイクルに統合され、ソケットファイルのリークが発生しない

**Independent Test**: `model.request()` を複数回呼び出し、各呼び出しの前後でソケットファイルが適切に作成・削除されることを確認する

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T019 [US2] Write tests for IPC lifecycle in `tests/test_ipc_integration.py`: IPC server auto-start before query, auto-stop after query completion, cleanup on exception (socket + schema file deleted), stale socket file detection and removal, multiple sequential requests succeed

### Implementation for User Story 2

- [ ] T020 [US2] Implement IPC server auto-start/stop in `request()` and `request_with_metadata()` with `try/finally`-based cleanup in `src/claudecode_model/model.py`
- [ ] T021 [US2] Implement IPC server auto-start/stop in `stream_messages()` with `try/finally`-based cleanup in `src/claudecode_model/model.py`
- [ ] T022 [P] [US2] Implement stale socket detection (scan `tempdir` for `claudecode_ipc_*.sock`) and cleanup at `IPCSession.start()` in `src/claudecode_model/ipc/server.py`
- [ ] T023 [US2] Verify socket file permissions are set to `0o600` after `asyncio.start_unix_server` bind in `src/claudecode_model/ipc/server.py`

**Checkpoint**: `request()`/`stream_messages()`/`request_with_metadata()` 呼び出し後にソケットファイルが残存しない。例外時もクリーンアップが保証される

---

## Phase 6: User Story 3 - トランスポート方式の選択 (Priority: P2)

**Goal**: `transport` パラメータにより IPC ブリッジ方式と従来 SDK 方式を切り替え可能にする

**Independent Test**: `transport="stdio"` と `transport="sdk"` をそれぞれ指定し、対応する MCP サーバー設定が生成されることを確認する

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T024 [US3] Write tests for transport selection in `tests/test_ipc_integration.py`: `transport="stdio"` → McpStdioServerConfig, `transport="sdk"` → McpSdkServerConfig (既存動作), `transport="auto"` → McpStdioServerConfig (stdio equivalent), default transport is "auto"

### Implementation for User Story 3

- [ ] T025 [US3] Add `transport: TransportType = DEFAULT_TRANSPORT` keyword argument to `set_agent_toolsets()` and implement routing logic (sdk → existing `create_mcp_server_from_tools()`, stdio/auto → IPC bridge) in `src/claudecode_model/model.py`
- [ ] T026 [US3] Update `_process_function_tools()` to preserve transport mode when re-filtering tools and regenerating MCP server config in `src/claudecode_model/model.py`

**Checkpoint**: `transport="sdk"` で既存動作が維持され、`transport="stdio"` で IPC ブリッジが使用される

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 品質保証とドキュメント整合性

- [ ] T027 Run quality checks: `ruff check --fix . && ruff format . && mypy .` — resolve all errors
- [ ] T028 Validate `specs/006-ipc-bridge/quickstart.md` scenarios against implementation
- [ ] T029 Final review of `src/claudecode_model/__init__.py` exports: ensure all new public types (`TransportType`, `DEFAULT_TRANSPORT`) and exceptions (`IPCError`, `IPCConnectionError`, `IPCMessageSizeError`, `IPCToolExecutionError`, `BridgeStartupError`) are exported

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **US4 (Phase 3)**: Depends on Phase 2 (uses protocol module)
- **US1 (Phase 4)**: Depends on Phase 2 (uses protocol module). Independent of US4 for implementation but shares protocol layer
- **US2 (Phase 5)**: Depends on Phase 4 (requires IPCServer and IPCSession)
- **US3 (Phase 6)**: Depends on Phase 4 (requires IPC bridge integration in model.py)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US4 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories. Independently testable via stdin/stdout
- **US1 (P1)**: Can start after Foundational (Phase 2) - Can be implemented in parallel with US4 if both start from protocol layer. Independently testable with manual IPC server + bridge
- **US2 (P1)**: Depends on US1 (Phase 4) - Requires IPCServer/IPCSession to exist for lifecycle integration
- **US3 (P2)**: Depends on US1 (Phase 4) - Requires IPC bridge integration to add transport routing on top

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD Red-Green)
- Protocol types before framing logic
- Server/Bridge core before integration
- Core implementation before edge cases (stale detection, permissions)

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 can run in parallel (different files)
- **Phase 2**: T006 can run in parallel with other non-dependent work
- **Phase 3**: T009, T010 can run in parallel (different concerns within bridge.py, but same file — coordinate)
- **Phase 4**: T016 can run in parallel with T014/T015 (different file: mcp_integration.py vs server.py)
- **Phase 5**: T022 can run in parallel with T020/T021 (server.py vs model.py)
- **US4 + US1**: Can be worked on in parallel by different developers after Phase 2

---

## Parallel Example: Phase 2 + Phase 3

```bash
# After Phase 2 completes, US4 and US1 can start in parallel:

# Developer A: US4 (Bridge Process)
Task: "Write tests for bridge process in tests/test_ipc_bridge.py"
Task: "Implement schema loading and tools/list in bridge.py"
Task: "Implement IPC client with lazy connect in bridge.py"

# Developer B: US1 (IPC Server)
Task: "Write tests for IPC server in tests/test_ipc_server.py"
Task: "Implement IPCServer with asyncio Unix socket in server.py"
Task: "Implement IPCSession with path generation in server.py"
```

---

## Implementation Strategy

### MVP First (US4 + US1)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Protocol (T005-T007)
3. Complete Phase 3: US4 Bridge Process (T008-T011)
4. Complete Phase 4: US1 IPC Server + Integration (T012-T018)
5. **STOP and VALIDATE**: ツールが CLI 経由で呼び出し可能であることを確認
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Protocol → Foundation ready
2. US4 (Bridge) → ブリッジプロセスが独立動作確認 (milestone)
3. US1 (Server + Integration) → ツール実行が E2E で動作 (MVP!)
4. US2 (Lifecycle) → リソースリーク防止が保証
5. US3 (Transport) → 方式切り替え可能
6. Polish → 品質保証完了

### Recommended Single-Developer Order

US4 → US1 → US2 → US3 → Polish

US4 を先に実装することで、ブリッジプロセスの動作を独立テスト可能。その後 US1 で IPC サーバーを実装し、US4 と結合テスト。US2 でライフサイクルを統合し、US3 でトランスポート選択を追加。

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD Red phase)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution Art.1: テストファースト必須、Art.5: 品質チェック必須、Art.9: 型注釈必須
