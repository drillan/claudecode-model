"""Tests for ClaudeCodeModel core functionality."""

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)

from claudecode_model.cli import DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS
from claudecode_model.model import ClaudeCodeModel


class TestClaudeCodeModelInit:
    """Tests for ClaudeCodeModel initialization."""

    def test_default_values(self) -> None:
        """ClaudeCodeModel should use default values."""
        model = ClaudeCodeModel()
        assert model.model_name == DEFAULT_MODEL
        assert model._timeout == DEFAULT_TIMEOUT_SECONDS
        assert model._working_directory is None
        assert model._allowed_tools is None
        assert model._disallowed_tools is None
        assert model._permission_mode is None

    def test_custom_values(self) -> None:
        """ClaudeCodeModel should accept custom values."""
        model = ClaudeCodeModel(
            model_name="claude-opus-4",
            working_directory="/tmp",
            timeout=60.0,
            allowed_tools=["Read"],
            disallowed_tools=["Bash"],
            permission_mode="bypassPermissions",
        )
        assert model.model_name == "claude-opus-4"
        assert model._working_directory == "/tmp"
        assert model._timeout == 60.0
        assert model._allowed_tools == ["Read"]
        assert model._disallowed_tools == ["Bash"]
        assert model._permission_mode == "bypassPermissions"

    def test_max_turns_default_to_none(self) -> None:
        """ClaudeCodeModel max_turns should default to None."""
        model = ClaudeCodeModel()
        assert model._max_turns is None

    def test_max_turns_accepts_positive_value(self) -> None:
        """ClaudeCodeModel should accept positive max_turns."""
        model = ClaudeCodeModel(max_turns=5)
        assert model._max_turns == 5


class TestClaudeCodeModelProperties:
    """Tests for ClaudeCodeModel properties."""

    def test_model_name_property(self) -> None:
        """model_name property should return the model name."""
        model = ClaudeCodeModel(model_name="test-model")
        assert model.model_name == "test-model"

    def test_system_property(self) -> None:
        """system property should return 'claude-code'."""
        model = ClaudeCodeModel()
        assert model.system == "claude-code"


class TestClaudeCodeModelProfile:
    """Tests for ClaudeCodeModel profile configuration."""

    def test_profile_supports_json_schema_output(self) -> None:
        """ClaudeCodeModel profile should support JSON schema output."""
        model = ClaudeCodeModel()
        assert model.profile.supports_json_schema_output is True

    def test_profile_default_structured_output_mode_is_native(self) -> None:
        """ClaudeCodeModel profile should default to native output mode."""
        model = ClaudeCodeModel()
        assert model.profile.default_structured_output_mode == "native"

    def test_profile_is_cached(self) -> None:
        """ClaudeCodeModel profile should be cached (same instance)."""
        model = ClaudeCodeModel()
        profile1 = model.profile
        profile2 = model.profile
        assert profile1 is profile2


class TestClaudeCodeModelRepr:
    """Tests for ClaudeCodeModel __repr__."""

    def test_repr(self) -> None:
        """__repr__ should return a readable representation."""
        model = ClaudeCodeModel(model_name="test-model")
        assert repr(model) == "ClaudeCodeModel(model_name='test-model')"


class TestClaudeCodeModelExtractSystemPrompt:
    """Tests for ClaudeCodeModel._extract_system_prompt method."""

    def test_extracts_system_prompt(self) -> None:
        """_extract_system_prompt should extract system prompt from messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="You are helpful."),
                    UserPromptPart(content="Hello"),
                ]
            )
        ]
        result = model._extract_system_prompt(messages)
        assert result == "You are helpful."

    def test_returns_none_when_no_system_prompt(self) -> None:
        """_extract_system_prompt should return None when no system prompt."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        result = model._extract_system_prompt(messages)
        assert result is None

    def test_returns_first_system_prompt(self) -> None:
        """_extract_system_prompt should return the first system prompt found."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="First"),
                    SystemPromptPart(content="Second"),
                ]
            )
        ]
        result = model._extract_system_prompt(messages)
        assert result == "First"


class TestClaudeCodeModelExtractUserPrompt:
    """Tests for ClaudeCodeModel._extract_user_prompt method."""

    def test_extracts_user_prompt(self) -> None:
        """_extract_user_prompt should extract user prompt from messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Hello"

    def test_joins_multiple_user_prompts(self) -> None:
        """_extract_user_prompt should join multiple user prompts."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    UserPromptPart(content="Hello"),
                    UserPromptPart(content="World"),
                ]
            )
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Hello\nWorld"

    def test_raises_on_empty_messages(self) -> None:
        """_extract_user_prompt should raise ValueError on empty messages."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = []
        with pytest.raises(ValueError, match="No user prompt found"):
            model._extract_user_prompt(messages)

    def test_raises_on_no_user_prompt(self) -> None:
        """_extract_user_prompt should raise ValueError when no user prompt."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content="System")])
        ]
        with pytest.raises(ValueError, match="No user prompt found"):
            model._extract_user_prompt(messages)

    def test_handles_list_content(self) -> None:
        """_extract_user_prompt should handle list content."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(
                parts=[
                    UserPromptPart(content=["Part 1", "Part 2"]),  # type: ignore[arg-type]
                ]
            )
        ]
        result = model._extract_user_prompt(messages)
        assert result == "Part 1\nPart 2"
