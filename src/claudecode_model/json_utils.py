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
        ValueError: If no valid JSON found, with details of each strategy's failure
    """
    text_stripped = text.strip()
    failures: list[str] = []

    # Strategy 1: Direct JSON parse
    try:
        result = json.loads(text_stripped)
        if isinstance(result, dict):
            return result
        return {"value": result}  # Wrap non-dict in dict
    except json.JSONDecodeError as e:
        failures.append(f"direct parse: {e}")

    # Strategy 2: Extract from ```json ... ``` blocks
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict):
                return result
            return {"value": result}
        except json.JSONDecodeError as e:
            failures.append(f"code block: {e}")
    else:
        failures.append("code block: no ```json``` block found")

    # Strategy 3: Find JSON object pattern (greedy, handles nested)
    # Use bracket counting approach
    obj_result = _find_json_object(text, failures)
    if obj_result is not None:
        return obj_result

    # Strategy 4: Find JSON array pattern
    arr_result = _find_json_array(text, failures)
    if arr_result is not None:
        return {"value": arr_result}

    # Truncate text for error message
    preview = text[:200] + "..." if len(text) > 200 else text
    failure_details = "; ".join(failures)
    raise ValueError(
        f"No valid JSON found in output. Strategies tried: [{failure_details}]. "
        f"Text preview: {preview}"
    )


def _find_json_object(
    text: str, failures: list[str] | None = None
) -> dict[str, JsonValue] | None:
    """Find and parse the first JSON object {...} in text.

    Uses bracket counting to handle nested objects and tracks string context
    to correctly handle braces inside strings.

    Args:
        text: Text to search
        failures: Optional list to append failure reasons to

    Returns:
        Parsed JSON dict or None if not found
    """
    found_brace = False
    last_error: str | None = None

    for i, char in enumerate(text):
        if char == "{":
            found_brace = True
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
                        except json.JSONDecodeError as e:
                            last_error = str(e)
                            # Continue searching for next object
                            break
            # If we get here without returning, this { didn't lead to valid JSON
            # Continue to find next {

    if failures is not None:
        if not found_brace:
            failures.append("object pattern: no '{' found")
        elif last_error:
            failures.append(f"object pattern: {last_error}")
        else:
            failures.append("object pattern: unclosed or invalid structure")

    return None


def _find_json_array(
    text: str, failures: list[str] | None = None
) -> list[JsonValue] | None:
    """Find and parse the first JSON array [...] in text.

    Uses bracket counting to handle nested arrays and tracks string context
    to correctly handle brackets inside strings.

    Args:
        text: Text to search
        failures: Optional list to append failure reasons to

    Returns:
        Parsed JSON list or None if not found
    """
    found_bracket = False
    last_error: str | None = None

    for i, char in enumerate(text):
        if char == "[":
            found_bracket = True
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
                        except json.JSONDecodeError as e:
                            last_error = str(e)
                            # Continue searching for next array
                            break
            # If we get here without returning, this [ didn't lead to valid JSON
            # Continue to find next [

    if failures is not None:
        if not found_bracket:
            failures.append("array pattern: no '[' found")
        elif last_error:
            failures.append(f"array pattern: {last_error}")
        else:
            failures.append("array pattern: unclosed or invalid structure")

    return None
