"""File analysis example using Claude Code's built-in tools."""

import asyncio

from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel


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
    asyncio.run(main())
