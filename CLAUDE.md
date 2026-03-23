# CLAUDE.md

## CLI/Plugin設計

- `--help`: 明確な使用方法
- `--non-interactive`: 非対話モード対応
- エラー: 解決方法を含める
- 終了コード: 0=成功, 非0=失敗

## GitHub CLI (gh)

- Claude Code on the Webでは`-R owner/repo`フラグが必須
- 例: `gh pr list -R owner/repo`, `gh issue view 123 -R owner/repo`

## 命名規則

- 詳細: `.claude/git-conventions.md`
- specs/: `<3桁通し番号>-<name>`（例: `001-architecture`）
- ブランチ: ゼロパディングなし

## Active Technologies
- Python 3.13+, pydantic-ai, claude-agent-sdk, mcp
- uv (パッケージ管理)

## Recent Changes
