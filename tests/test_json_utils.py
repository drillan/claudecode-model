"""Tests for claudecode_model.json_utils module."""

import pytest

from claudecode_model.json_utils import (
    _find_json_structure,
    extract_json,
)


class TestExtractJsonDirectParse:
    """Tests for direct JSON parsing."""

    def test_extract_json_direct_parse_object(self) -> None:
        """extract_json should parse JSON object directly."""
        text = '{"name": "test", "value": 42}'
        result = extract_json(text)
        assert result == {"name": "test", "value": 42}

    def test_extract_json_direct_parse_with_whitespace(self) -> None:
        """extract_json should parse JSON with leading/trailing whitespace."""
        text = '  \n{"name": "test"}\n  '
        result = extract_json(text)
        assert result == {"name": "test"}

    def test_extract_json_direct_parse_array_wraps_in_dict(self) -> None:
        """extract_json should wrap array result in dict with 'value' key."""
        text = "[1, 2, 3]"
        result = extract_json(text)
        assert result == {"value": [1, 2, 3]}

    def test_extract_json_direct_parse_nested(self) -> None:
        """extract_json should parse nested JSON objects."""
        text = '{"user": {"name": "Alice", "age": 30}, "active": true}'
        result = extract_json(text)
        assert result == {"user": {"name": "Alice", "age": 30}, "active": True}


class TestExtractJsonCodeBlock:
    """Tests for JSON extraction from markdown code blocks."""

    def test_extract_json_from_code_block(self) -> None:
        """extract_json should extract JSON from ```json code block."""
        text = """Here is the result:
```json
{"status": "success", "data": [1, 2, 3]}
```
Done."""
        result = extract_json(text)
        assert result == {"status": "success", "data": [1, 2, 3]}

    def test_extract_json_from_code_block_with_extra_whitespace(self) -> None:
        """extract_json should handle code block with extra whitespace."""
        text = """Result:
```json

  {"key": "value"}

```"""
        result = extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_from_code_block_array(self) -> None:
        """extract_json should extract array from code block and wrap in dict."""
        text = """```json
["a", "b", "c"]
```"""
        result = extract_json(text)
        assert result == {"value": ["a", "b", "c"]}


class TestExtractJsonObjectPattern:
    """Tests for JSON object pattern extraction."""

    def test_extract_json_find_object_in_text(self) -> None:
        """extract_json should find JSON object in surrounding text."""
        text = 'The result is: {"score": 95, "grade": "A"} as expected.'
        result = extract_json(text)
        assert result == {"score": 95, "grade": "A"}

    def test_extract_json_find_nested_object(self) -> None:
        """extract_json should find nested JSON object."""
        text = 'Output: {"outer": {"inner": {"deep": 1}}}'
        result = extract_json(text)
        assert result == {"outer": {"inner": {"deep": 1}}}

    def test_extract_json_find_object_with_arrays(self) -> None:
        """extract_json should find object containing arrays."""
        text = 'Data: {"items": [{"id": 1}, {"id": 2}], "count": 2}'
        result = extract_json(text)
        assert result == {"items": [{"id": 1}, {"id": 2}], "count": 2}


class TestExtractJsonArrayPattern:
    """Tests for JSON array pattern extraction."""

    def test_extract_json_find_array_in_text(self) -> None:
        """extract_json should find JSON array in text and wrap in dict."""
        text = "The items are: [1, 2, 3, 4, 5] in order."
        result = extract_json(text)
        assert result == {"value": [1, 2, 3, 4, 5]}

    def test_extract_json_find_nested_array(self) -> None:
        """extract_json should find nested arrays."""
        text = "Matrix: [[1, 2], [3, 4]]"
        result = extract_json(text)
        assert result == {"value": [[1, 2], [3, 4]]}

    def test_extract_json_find_array_of_objects(self) -> None:
        """extract_json should find array of objects when array comes first."""
        # Note: When array contains objects, the first object is found due to
        # object-over-array priority. To get an array of objects, ensure the
        # array appears as standalone JSON.
        text = '[{"name": "Alice"}, {"name": "Bob"}]'
        result = extract_json(text)
        assert result == {"value": [{"name": "Alice"}, {"name": "Bob"}]}


class TestExtractJsonErrors:
    """Tests for error handling."""

    def test_extract_json_raises_on_invalid_input(self) -> None:
        """extract_json should raise ValueError on invalid input."""
        text = "This is just plain text with no JSON."
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json(text)

    def test_extract_json_raises_on_empty_string(self) -> None:
        """extract_json should raise ValueError on empty string."""
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json("")

    def test_extract_json_raises_on_malformed_json(self) -> None:
        """extract_json should raise ValueError on malformed JSON."""
        text = '{"unclosed": "brace"'
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json(text)

    def test_extract_json_raises_on_incomplete_code_block(self) -> None:
        """extract_json should raise ValueError if code block has invalid JSON."""
        text = """```json
{"incomplete":
```"""
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json(text)


class TestExtractJsonPriority:
    """Tests for extraction priority (direct > code block > pattern)."""

    def test_direct_parse_takes_priority_over_pattern(self) -> None:
        """extract_json should prefer direct parse over pattern matching."""
        # This is valid JSON directly
        text = '{"direct": true}'
        result = extract_json(text)
        assert result == {"direct": True}

    def test_code_block_takes_priority_over_pattern(self) -> None:
        """extract_json should prefer code block over pattern matching."""
        # This has both a code block and a pattern in surrounding text
        text = """Found: {"pattern": 1}
```json
{"codeblock": 2}
```"""
        result = extract_json(text)
        # Code block should be found after direct parse fails
        assert result == {"codeblock": 2}

    def test_object_pattern_takes_priority_over_array(self) -> None:
        """extract_json should prefer object pattern over array pattern."""
        # Has both object and array
        text = 'Array [1, 2] and Object {"obj": true}'
        result = extract_json(text)
        # Object pattern should be found first
        assert result == {"obj": True}


class TestExtractJsonEdgeCases:
    """Tests for edge cases."""

    def test_extract_json_with_unicode(self) -> None:
        """extract_json should handle Unicode characters."""
        text = '{"message": "Hello, \u4e16\u754c!"}'
        result = extract_json(text)
        assert result == {"message": "Hello, \u4e16\u754c!"}

    def test_extract_json_with_special_characters(self) -> None:
        """extract_json should handle special characters in strings."""
        text = r'{"path": "C:\\Users\\test", "tab": "\t"}'
        result = extract_json(text)
        assert result["path"] == "C:\\Users\\test"

    def test_extract_json_with_null_values(self) -> None:
        """extract_json should handle null values."""
        text = '{"value": null, "list": [null, 1, null]}'
        result = extract_json(text)
        assert result == {"value": None, "list": [None, 1, None]}

    def test_extract_json_with_boolean_values(self) -> None:
        """extract_json should handle boolean values."""
        text = '{"active": true, "deleted": false}'
        result = extract_json(text)
        assert result == {"active": True, "deleted": False}

    def test_extract_json_with_numbers(self) -> None:
        """extract_json should handle various number formats."""
        text = '{"int": 42, "float": 3.14, "negative": -10, "exp": 1e5}'
        result = extract_json(text)
        assert result == {"int": 42, "float": 3.14, "negative": -10, "exp": 100000.0}

    def test_extract_json_with_empty_object(self) -> None:
        """extract_json should handle empty object."""
        text = "{}"
        result = extract_json(text)
        assert result == {}

    def test_extract_json_with_empty_array(self) -> None:
        """extract_json should handle empty array."""
        text = "[]"
        result = extract_json(text)
        assert result == {"value": []}


class TestFindJsonStructureInternal:
    """Tests for internal _find_json_structure function."""

    def test_find_object_basic(self) -> None:
        """Test finding basic JSON object."""
        text = 'Some text {"key": "value"} more text'
        result = _find_json_structure(text, "{", "}", "object")
        assert result == {"key": "value"}

    def test_find_array_basic(self) -> None:
        """Test finding basic JSON array."""
        text = "Some text [1, 2, 3] more text"
        result = _find_json_structure(text, "[", "]", "array")
        assert result == [1, 2, 3]

    def test_find_nested_structure(self) -> None:
        """Test finding nested structures."""
        text = 'Output: {"outer": {"inner": {"deep": 1}}}'
        result = _find_json_structure(text, "{", "}", "object")
        assert result == {"outer": {"inner": {"deep": 1}}}

    def test_find_with_escaped_quotes(self) -> None:
        """Test handling escaped quotes in strings."""
        text = r'Data: {"text": "He said \"hello\""}'
        result = _find_json_structure(text, "{", "}", "object")
        assert result == {"text": 'He said "hello"'}

    def test_find_no_structure_found(self) -> None:
        """Test failure message when no structure found."""
        text = "No JSON here"
        failures: list[str] = []
        result = _find_json_structure(text, "{", "}", "object", failures)
        assert result is None
        assert len(failures) == 1
        assert "object pattern: no '{' found" in failures[0]

    def test_find_unclosed_structure(self) -> None:
        """Test failure message for unclosed structure."""
        text = '{"unclosed": true'
        failures: list[str] = []
        result = _find_json_structure(text, "{", "}", "object", failures)
        assert result is None
        assert len(failures) == 1
        assert "object pattern: unclosed or invalid structure" in failures[0]
