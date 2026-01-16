"""Structured output example - manual JSON parsing approach.

Note: ClaudeCodeModel does not support pydantic-ai's native output_type
parameter for structured output. This example demonstrates how to achieve
structured output by prompting for JSON and parsing manually.

Prerequisites:
    - Claude Code CLI installed and available in PATH
    - Valid authentication configured for Claude Code CLI
"""

import asyncio
import json
import sys

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel
from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
)


class CodeReview(BaseModel):
    """Code review result structure."""

    file_name: str
    issues: list[str]
    suggestions: list[str]
    score: int = Field(ge=1, le=10)


async def main() -> None:
    """Run an agent that returns structured output via JSON."""
    model = ClaudeCodeModel(
        model_name="claude-sonnet-4-5",
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob"],
    )

    # Agent[None, str]で文字列として受け取り、手動でJSONをパースする
    agent: Agent[None, str] = Agent(
        model,
        system_prompt=(
            "あなたはコードレビューの専門家です。"
            "与えられたコードを分析し、以下のJSON形式のみで回答してください。"
            "説明文は不要です。JSONのみを出力してください。\n"
            '{"file_name": "ファイル名", "issues": ["問題1", "問題2"], '
            '"suggestions": ["提案1", "提案2"], "score": 1-10の数値}'
        ),
    )

    code_to_review = """
def calc(x,y):
    return x+y if x>0 else y-x
"""

    result = await agent.run(
        f"以下のコードをレビューしてJSON形式で回答してください:\n```python\n{code_to_review}\n```"
    )

    # レスポンスからJSONを抽出
    raw_output = result.output
    print("=== Raw Output ===")
    print(raw_output)
    print()

    # JSONブロックを抽出（```json ... ``` または直接JSON）
    json_str = raw_output.strip()
    if json_str.startswith("```"):
        # コードブロックからJSONを抽出
        lines = json_str.split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            if line.startswith("```json"):
                in_json = True
                continue
            if line.startswith("```") and in_json:
                break
            if in_json:
                json_lines.append(line)
        json_str = "\n".join(json_lines)

    try:
        data = json.loads(json_str)
        review = CodeReview.model_validate(data)

        print("=== Parsed Code Review ===")
        print(f"File: {review.file_name}")
        print(f"Score: {review.score}/10")
        print()
        print("Issues:")
        for issue in review.issues:
            print(f"  - {issue}")
        print()
        print("Suggestions:")
        for suggestion in review.suggestions:
            print(f"  - {suggestion}")
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}", file=sys.stderr)
        print(f"Raw output was: {raw_output}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        sys.exit(1)


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
