"""JSON extraction utilities for structured output."""

from __future__ import annotations

import json
import re

from claudecode_model.types import JsonValue


def extract_json(text: str) -> dict[str, JsonValue]:
    """Extract JSON from CLI output text.

    Attempts multiple strategies in order:
    1. Parse text directly as JSON
    2. Extract from ```json ... ``` code blocks
    3. Find first {...} pattern (JSON object)
    4. Find first [...] pattern (JSON array)

    Args:
        text: Raw CLI output text

    Returns:
        Parsed JSON as dictionary. Arrays are wrapped in {"value": ...}

    Raises:
        ValueError: If no valid JSON found
    """
    text_stripped = text.strip()

    # Strategy 1: Direct JSON parse
    try:
        result = json.loads(text_stripped)
        if isinstance(result, dict):
            return result
        return {"value": result}  # Wrap non-dict in dict
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from ```json ... ``` blocks
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict):
                return result
            return {"value": result}
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find JSON object pattern (greedy, handles nested)
    # Use bracket counting approach
    obj_result = _find_json_object(text)
    if obj_result is not None:
        return obj_result

    # Strategy 4: Find JSON array pattern
    arr_result = _find_json_array(text)
    if arr_result is not None:
        return {"value": arr_result}

    # Truncate text for error message
    preview = text[:200] + "..." if len(text) > 200 else text
    raise ValueError(f"No valid JSON found in output: {preview}")


def _find_json_object(text: str) -> dict[str, JsonValue] | None:
    """Find and parse the first JSON object {...} in text.

    Args:
        text: Text to search

    Returns:
        Parsed JSON dict or None if not found
    """
    for i, char in enumerate(text):
        if char == "{":
            depth = 1
            in_string = False
            escape_next = False

            for j in range(i + 1, len(text)):
                c = text[j]

                if escape_next:
                    escape_next = False
                    continue

                if c == "\\":
                    escape_next = True
                    continue

                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i : j + 1])
                        except json.JSONDecodeError:
                            # Continue searching for next object
                            break
            # If we get here without returning, this { didn't lead to valid JSON
            # Continue to find next {
    return None


def _find_json_array(text: str) -> list[JsonValue] | None:
    """Find and parse the first JSON array [...] in text.

    Args:
        text: Text to search

    Returns:
        Parsed JSON list or None if not found
    """
    for i, char in enumerate(text):
        if char == "[":
            depth = 1
            in_string = False
            escape_next = False

            for j in range(i + 1, len(text)):
                c = text[j]

                if escape_next:
                    escape_next = False
                    continue

                if c == "\\":
                    escape_next = True
                    continue

                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i : j + 1])
                        except json.JSONDecodeError:
                            # Continue searching for next array
                            break
            # If we get here without returning, this [ didn't lead to valid JSON
            # Continue to find next [
    return None
