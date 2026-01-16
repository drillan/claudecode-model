"""File analysis example using Claude Code's built-in tools.

Prerequisites:
    - Claude Code CLI installed and available in PATH
    - Valid authentication configured for Claude Code CLI
"""

import asyncio
import sys

from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel
from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
)


async def main() -> None:
    """Run an agent that analyzes files in the current directory."""
    model = ClaudeCodeModel(
        model_name="claude-sonnet-4-5",
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep"],
        working_directory=".",  # Current directory
    )

    agent: Agent[None, str] = Agent(
        model,
        system_prompt=(
            "あなたはコードベース分析の専門家です。"
            "ファイルを読み取り、構造を理解し、わかりやすく説明してください。"
        ),
    )

    result = await agent.run(
        "このディレクトリにあるPythonファイルの構造を分析し、"
        "主要なクラスと関数を一覧してください。"
    )

    print("=== Analysis Result ===")
    print(result.output)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except CLINotFoundError as e:
        print(f"CLI not found: {e}", file=sys.stderr)
        sys.exit(1)
    except CLIExecutionError as e:
        print(f"CLI execution failed: {e}", file=sys.stderr)
        sys.exit(1)
    except CLIResponseParseError as e:
        print(f"Failed to parse CLI response: {e}", file=sys.stderr)
        sys.exit(1)
