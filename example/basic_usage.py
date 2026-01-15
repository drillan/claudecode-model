"""Basic usage example for claudecode-model."""

import asyncio

from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel


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
    asyncio.run(main())
