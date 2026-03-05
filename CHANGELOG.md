# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.0.37] - 2026-03-05

### Fixed

- CancelScope 衝突後の後続 SDK リクエストが `Unknown error` で失敗する問題を修正 (#148)
  - 空 result の SDK エラー (`is_error=True`, `result=None/""`) を `recoverable=True` に分類し、呼び出し側でリトライ判断可能に
  - `_had_cancel_scope_conflict` フラグで CancelScope 衝突と後続エラーの相関を診断ログに記録
  - ストリーミング正常完了時・非空エラー時にフラグをクリアし、誤った相関 warning を防止

## [0.0.36] - 2026-03-04

### Fixed

- IPC サーバーで IPCError を正常な切断として処理するよう修正

### Changed

- 依存関係の更新

## [0.0.35] - 2026-03-04

### Changed

- claude-agent-sdk 依存関係ハッシュの更新

## [0.0.34] - 2026-03-03

### Fixed

- CancelScope エラー回復時の query_generator クリーンアップを確実に実行するよう修正 (#147)

## [0.0.33] - 2026-03-03

### Fixed

- IPC ソケットクリーンアップの競合状態を防止 (#146)

## [0.0.32] - 2026-03-02

### Fixed

- CancelScope RuntimeError 発生時に成功したクエリ結果を保持するよう修正 (#144, #145)

## [0.0.31] - 2026-03-01

### Changed

- claude-agent-sdk の更新

## [0.0.30] - 2026-02-28

### Fixed

- anyio CancelScope と pydantic-graph のネスト衝突を解決 (#143)

## [0.0.29] - 2026-02-27

### Added

- Bash パラメータ制約を強制する `tool_parameter_restrictions` 機能 (#141)

### Fixed

- `run_query()` で ResultMessage 受信時にループを抜けるよう修正し、ブロッキングを防止 (#138, #140)
