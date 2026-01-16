"""Basic usage example for claudecode-model.

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
    """Run a simple agent with ClaudeCodeModel."""
    model = ClaudeCodeModel(
        model_name="claude-sonnet-4-5",
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    agent: Agent[None, str] = Agent(
        model,
        system_prompt="あなたは優秀なアシスタントです。簡潔に回答してください。",
    )

    result = await agent.run("1+1は何ですか？")

    print("=== Result ===")
    print(result.output)
    print()
    print("=== Usage ===")
    usage = result.usage()
    print(f"Input tokens: {usage.input_tokens}")
    print(f"Output tokens: {usage.output_tokens}")


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
