"""Tests for ClaudeCodeModel session options (continue_conversation, resume)."""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from claudecode_model.model import ClaudeCodeModel

from .conftest import create_mock_result_message


class TestClaudeCodeModelContinueConversationInit:
    """Tests for ClaudeCodeModel continue_conversation initialization."""

    def test_default_value(self) -> None:
        """continue_conversation should default to False."""
        model = ClaudeCodeModel()
        assert model._continue_conversation is False

    def test_accepts_true(self) -> None:
        """continue_conversation should accept True."""
        model = ClaudeCodeModel(continue_conversation=True)
        assert model._continue_conversation is True

    def test_accepts_false(self) -> None:
        """continue_conversation should accept False explicitly."""
        model = ClaudeCodeModel(continue_conversation=False)
        assert model._continue_conversation is False


class TestClaudeCodeModelContinueConversationFromModelSettings:
    """Tests for continue_conversation from model_settings."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.mark.asyncio
    async def test_uses_continue_conversation_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use continue_conversation from model_settings."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"continue_conversation": True}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].continue_conversation is True

    @pytest.mark.asyncio
    async def test_model_settings_overrides_init(
        self, mock_result_message: ResultMessage
    ) -> None:
        """model_settings continue_conversation should override init value."""
        model = ClaudeCodeModel(continue_conversation=False)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"continue_conversation": True}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].continue_conversation is True

    @pytest.mark.asyncio
    async def test_uses_init_when_not_in_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use init continue_conversation when not in model_settings."""
        model = ClaudeCodeModel(continue_conversation=True)
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, None, params)

            assert len(captured_options) == 1
            assert captured_options[0].continue_conversation is True

    def test_warns_on_invalid_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """_extract_model_settings should warn on invalid continue_conversation type."""
        import logging

        model = ClaudeCodeModel()
        settings = {"continue_conversation": "not_a_bool"}

        with caplog.at_level(logging.WARNING):
            result = model._extract_model_settings(settings)  # type: ignore[arg-type]

        # Should fall back to instance default (False)
        assert result.continue_conversation is False
        assert "invalid type" in caplog.text.lower()


class TestClaudeCodeModelResumeFromModelSettings:
    """Tests for resume from model_settings."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.mark.asyncio
    async def test_uses_resume_from_model_settings(
        self, mock_result_message: ResultMessage
    ) -> None:
        """request should use resume from model_settings."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"resume": "session-123"}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            await model.request(messages, settings, params)  # type: ignore[arg-type]

            assert len(captured_options) == 1
            assert captured_options[0].resume == "session-123"

    def test_resume_none_by_default(self) -> None:
        """_extract_model_settings should return None for resume by default."""
        model = ClaudeCodeModel()
        result = model._extract_model_settings(None)
        assert result.resume is None

    def test_warns_on_invalid_type_resume(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_extract_model_settings should warn on invalid resume type."""
        import logging

        model = ClaudeCodeModel()
        settings = {"resume": 123}  # Should be str, not int

        with caplog.at_level(logging.WARNING):
            result = model._extract_model_settings(settings)  # type: ignore[arg-type]

        # Should fall back to None
        assert result.resume is None
        assert "invalid type" in caplog.text.lower()


class TestClaudeCodeModelResumeAndContinueConversationMutualExclusion:
    """Tests for resume and continue_conversation mutual exclusion."""

    def test_raises_when_both_resume_and_continue_conversation_provided(self) -> None:
        """_extract_model_settings should raise ValueError when both are set."""
        model = ClaudeCodeModel()
        settings = {
            "resume": "session-123",
            "continue_conversation": True,
        }

        with pytest.raises(ValueError, match="resume.*continue_conversation"):
            model._extract_model_settings(settings)  # type: ignore[arg-type]

    def test_raises_when_init_continue_and_settings_resume(self) -> None:
        """Should raise ValueError when init has continue_conversation and settings has resume."""
        model = ClaudeCodeModel(continue_conversation=True)
        settings = {"resume": "session-123"}

        with pytest.raises(ValueError, match="resume.*continue_conversation"):
            model._extract_model_settings(settings)  # type: ignore[arg-type]


class TestClaudeCodeModelStreamMessagesWithSessionOptions:
    """Tests for stream_messages with session options."""

    @pytest.fixture
    def mock_result_message(self) -> ResultMessage:
        """Return a mock ResultMessage."""
        return create_mock_result_message()

    @pytest.mark.asyncio
    async def test_stream_messages_uses_continue_conversation(
        self, mock_result_message: ResultMessage
    ) -> None:
        """stream_messages should use continue_conversation from model_settings."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"continue_conversation": True}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model.stream_messages(messages, settings, params):  # type: ignore[arg-type]
                pass

            assert len(captured_options) == 1
            assert captured_options[0].continue_conversation is True

    @pytest.mark.asyncio
    async def test_stream_messages_uses_resume(
        self, mock_result_message: ResultMessage
    ) -> None:
        """stream_messages should use resume from model_settings."""
        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")])
        ]
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )
        settings = {"resume": "session-456"}

        captured_options: list[ClaudeAgentOptions] = []

        async def mock_query(
            prompt: str, options: ClaudeAgentOptions
        ) -> AsyncIterator[ResultMessage]:
            captured_options.append(options)
            yield mock_result_message

        with patch("claudecode_model.model.query", mock_query):
            async for _ in model.stream_messages(messages, settings, params):  # type: ignore[arg-type]
                pass

            assert len(captured_options) == 1
            assert captured_options[0].resume == "session-456"
