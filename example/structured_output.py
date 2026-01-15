"""Structured output example - manual JSON parsing approach."""

import asyncio
import json

from pydantic import BaseModel
from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel


class CodeReview(BaseModel):
    """Code review result structure."""

    file_name: str
    issues: list[str]
    suggestions: list[str]
    score: int  # 1-10


async def main() -> None:
    """Run an agent that returns structured output via JSON."""
    model = ClaudeCodeModel(
        model_name="claude-sonnet-4-5",
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob"],
    )

    # output_type=strでテキストとして受け取り、JSONをパースする
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
    except (json.JSONDecodeError, Exception) as e:
        print(f"Failed to parse JSON: {e}")
        print("Raw output was:")
        print(raw_output)


if __name__ == "__main__":
    asyncio.run(main())
