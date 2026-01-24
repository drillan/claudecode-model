"""Tests for structured debug logging functionality.

This module tests the debug logging points added to support
CLAUDECODE_MODEL_LOG_LEVEL=DEBUG environment variable for troubleshooting.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


@pytest.fixture
def restore_modules() -> Generator[None, None, None]:
    """Save and restore module state to prevent test pollution.

    Tests that remove claudecode_model modules from sys.modules and re-import
    them should use this fixture to ensure original modules are restored
    after each test so other tests' mocks work correctly.
    """
    import sys
    from types import ModuleType

    # Save original module state
    original_modules: dict[str, ModuleType] = {
        key: mod
        for key, mod in sys.modules.items()
        if key.startswith("claudecode_model")
    }

    yield

    # Remove any modules added during the test
    modules_to_remove = [
        key for key in sys.modules if key.startswith("claudecode_model")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Restore original modules
    sys.modules.update(original_modules)

    # Clear handlers added during the test
    logger = logging.getLogger("claudecode_model")
    logger.handlers.clear()


class TestLogLevelConfiguration:
    """Tests for CLAUDECODE_MODEL_LOG_LEVEL environment variable."""

    @pytest.fixture(autouse=True)
    def _restore_modules(self, restore_modules: None) -> None:
        """Auto-use the shared restore_modules fixture."""

    def test_log_level_set_from_env_debug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that log level is set to DEBUG when env var is DEBUG."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "DEBUG")

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert logger.level == logging.DEBUG

    def test_log_level_set_from_env_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that log level is set to INFO when env var is INFO."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "INFO")

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert logger.level == logging.INFO

    def test_log_level_defaults_to_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that log level defaults to WARNING when env var is not set."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        monkeypatch.delenv("CLAUDECODE_MODEL_LOG_LEVEL", raising=False)

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert logger.level == logging.WARNING

    def test_log_level_invalid_value_falls_back_to_warning_with_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid log level falls back to WARNING and emits a warning."""
        import sys
        import warnings

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "INVALID_LEVEL")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import claudecode_model  # noqa: F401

            # Verify warning was emitted
            assert len(w) == 1
            assert "Invalid CLAUDECODE_MODEL_LOG_LEVEL" in str(w[0].message)
            assert "INVALID_LEVEL" in str(w[0].message)
            assert "Using WARNING" in str(w[0].message)

        # Verify fallback to WARNING
        logger = logging.getLogger("claudecode_model")
        assert logger.level == logging.WARNING


class TestModelLogging:
    """Tests for debug logging in model.py."""

    def test_init_logs_initialization_parameters(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that ClaudeCodeModel.__init__ logs initialization parameters."""
        from claudecode_model.model import ClaudeCodeModel

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            ClaudeCodeModel(
                model_name="test-model",
                working_directory="/test/dir",
                timeout=60.0,
                permission_mode="default",
                max_turns=5,
            )

        assert any(
            "ClaudeCodeModel initialized" in record.message
            and "test-model" in record.message
            and "/test/dir" in record.message
            and "60.0" in record.message
            and "default" in record.message
            and "5" in record.message
            for record in caplog.records
        ), (
            f"Expected initialization log not found. Records: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.anyio
    async def test_execute_request_logs_start(self, caplog: LogCaptureFixture) -> None:
        """Test that _execute_request logs start information."""
        from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

        from claudecode_model.model import ClaudeCodeModel, _QueryResult

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="test prompt")])
        ]

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            with patch.object(model, "_execute_sdk_query") as mock_query:
                mock_result = MagicMock()
                mock_result.result = "test result"
                mock_result.is_error = False
                mock_result.subtype = "success"
                mock_result.duration_ms = 100
                mock_result.duration_api_ms = 80
                mock_result.num_turns = 1
                mock_result.session_id = "test-session"
                mock_result.total_cost_usd = 0.01
                mock_result.usage = {
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
                mock_result.structured_output = None
                mock_query.return_value = _QueryResult(
                    result_message=mock_result,
                    captured_structured_output_input=None,
                )

                await model._execute_request(messages, None, json_schema=None)

        assert any(
            "_execute_request started" in record.message
            and "num_messages=" in record.message
            for record in caplog.records
        ), (
            f"Expected start log not found. Records: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.anyio
    async def test_execute_request_logs_completion(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that _execute_request logs completion information."""
        from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

        from claudecode_model.model import ClaudeCodeModel, _QueryResult

        model = ClaudeCodeModel()
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="test prompt")])
        ]

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            with patch.object(model, "_execute_sdk_query") as mock_query:
                mock_result = MagicMock()
                mock_result.result = "test result"
                mock_result.is_error = False
                mock_result.subtype = "success"
                mock_result.duration_ms = 150
                mock_result.duration_api_ms = 120
                mock_result.num_turns = 2
                mock_result.session_id = "test-session"
                mock_result.total_cost_usd = 0.02
                mock_result.usage = {
                    "input_tokens": 200,
                    "output_tokens": 100,
                }
                mock_result.structured_output = {"key": "value"}
                mock_query.return_value = _QueryResult(
                    result_message=mock_result,
                    captured_structured_output_input=None,
                )

                await model._execute_request(messages, None, json_schema=None)

        assert any(
            "_execute_request completed" in record.message
            and "duration_ms=" in record.message
            and "num_turns=" in record.message
            for record in caplog.records
        ), (
            f"Expected completion log not found. Records: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.anyio
    async def test_execute_sdk_query_logs_start(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that _execute_sdk_query logs query parameters."""
        from claude_agent_sdk import ClaudeAgentOptions

        from claudecode_model.model import ClaudeCodeModel

        model = ClaudeCodeModel(model_name="test-model", timeout=30.0, max_turns=10)
        options = ClaudeAgentOptions(model="test-model", max_turns=10)

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            with patch("claudecode_model.model.query") as mock_query:

                async def mock_generator():
                    mock_result = MagicMock()
                    mock_result.result = "test"
                    mock_result.is_error = False
                    mock_result.subtype = "success"
                    mock_result.duration_ms = 100
                    mock_result.duration_api_ms = 80
                    mock_result.num_turns = 1
                    mock_result.session_id = "session"
                    mock_result.total_cost_usd = 0.01
                    mock_result.usage = {}
                    mock_result.structured_output = None
                    # Simulate ResultMessage
                    from claude_agent_sdk import ResultMessage

                    yield ResultMessage(
                        result="test",
                        is_error=False,
                        subtype="success",
                        duration_ms=100,
                        duration_api_ms=80,
                        num_turns=1,
                        session_id="session",
                        total_cost_usd=0.01,
                        usage={},
                    )

                mock_query.return_value = mock_generator()

                await model._execute_sdk_query(
                    prompt="test prompt", options=options, timeout=30.0
                )

        assert any(
            "_execute_sdk_query started" in record.message
            and "prompt_length=" in record.message
            and "timeout=" in record.message
            for record in caplog.records
        ), (
            f"Expected SDK query log not found. Records: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.anyio
    async def test_execute_sdk_query_logs_completion(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that _execute_sdk_query logs completion with token usage."""
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

        from claudecode_model.model import ClaudeCodeModel

        model = ClaudeCodeModel(model_name="test-model", timeout=30.0, max_turns=10)
        options = ClaudeAgentOptions(model="test-model", max_turns=10)

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            with patch("claudecode_model.model.query") as mock_query:

                async def mock_generator():
                    yield ResultMessage(
                        result="test result",
                        is_error=False,
                        subtype="success",
                        duration_ms=150,
                        duration_api_ms=120,
                        num_turns=2,
                        session_id="session-123",
                        total_cost_usd=0.02,
                        usage={"input_tokens": 500, "output_tokens": 200},
                    )

                mock_query.return_value = mock_generator()

                await model._execute_sdk_query(
                    prompt="test prompt", options=options, timeout=30.0
                )

        assert any(
            "_execute_sdk_query completed" in record.message
            and "num_turns=" in record.message
            and "duration_ms=" in record.message
            and "is_error=" in record.message
            and "input_tokens=" in record.message
            and "output_tokens=" in record.message
            for record in caplog.records
        ), (
            f"Expected SDK query completion log not found. "
            f"Records: {[r.message for r in caplog.records]}"
        )

    def test_process_function_tools_logs_tools(self, caplog: LogCaptureFixture) -> None:
        """Test that _process_function_tools logs tool information."""
        from claudecode_model.model import ClaudeCodeModel

        model = ClaudeCodeModel()

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool_a"
        mock_tool1.description = "Tool A"
        mock_tool1.parameters_json_schema = {"type": "object"}
        mock_tool1.function = AsyncMock()

        mock_tool2 = MagicMock()
        mock_tool2.name = "tool_b"
        mock_tool2.description = "Tool B"
        mock_tool2.parameters_json_schema = {"type": "object"}
        mock_tool2.function = AsyncMock()

        model.set_agent_toolsets([mock_tool1, mock_tool2])

        # Create mock ToolDefinitions
        mock_td1 = MagicMock()
        mock_td1.name = "tool_a"
        mock_td2 = MagicMock()
        mock_td2.name = "tool_b"

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            model._process_function_tools([mock_td1, mock_td2])

        assert any(
            "_process_function_tools" in record.message
            and "num_tools=" in record.message
            and "tool_names=" in record.message
            for record in caplog.records
        ), (
            f"Expected process tools log not found. Records: {[r.message for r in caplog.records]}"
        )

    def test_set_agent_toolsets_logs_registration(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that set_agent_toolsets logs tool registration."""
        from claudecode_model.model import ClaudeCodeModel

        model = ClaudeCodeModel()

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "my_tool_1"
        mock_tool1.description = "My Tool 1"
        mock_tool1.parameters_json_schema = {"type": "object"}
        mock_tool1.function = AsyncMock()

        mock_tool2 = MagicMock()
        mock_tool2.name = "my_tool_2"
        mock_tool2.description = "My Tool 2"
        mock_tool2.parameters_json_schema = {"type": "object"}
        mock_tool2.function = AsyncMock()

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.model"):
            model.set_agent_toolsets([mock_tool1, mock_tool2])

        assert any(
            "set_agent_toolsets" in record.message
            and "registered" in record.message
            and "2" in record.message
            for record in caplog.records
        ), (
            f"Expected registration log not found. Records: {[r.message for r in caplog.records]}"
        )


class TestMcpIntegrationLogging:
    """Tests for debug logging in mcp_integration.py."""

    def test_extract_tools_from_toolsets_logs_extraction(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that extract_tools_from_toolsets logs extracted tools."""
        from claudecode_model.mcp_integration import extract_tools_from_toolsets

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "extract_tool_1"
        mock_tool1.description = "Extract Tool 1"
        mock_tool1.parameters_json_schema = {"type": "object"}
        mock_tool1.function = AsyncMock()

        mock_tool2 = MagicMock()
        mock_tool2.name = "extract_tool_2"
        mock_tool2.description = "Extract Tool 2"
        mock_tool2.parameters_json_schema = {"type": "object"}
        mock_tool2.function = AsyncMock()

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.mcp_integration"):
            extract_tools_from_toolsets([mock_tool1, mock_tool2])

        assert any(
            "extract_tools_from_toolsets" in record.message
            and "extracted" in record.message
            and "2" in record.message
            for record in caplog.records
        ), (
            f"Expected extraction log not found. Records: {[r.message for r in caplog.records]}"
        )

    def test_create_mcp_server_from_tools_logs_creation(
        self, caplog: LogCaptureFixture
    ) -> None:
        """Test that create_mcp_server_from_tools logs server creation."""
        from claudecode_model.mcp_integration import create_mcp_server_from_tools

        # Create mock tools
        mock_tool = MagicMock()
        mock_tool.name = "server_tool"
        mock_tool.description = "Server Tool"
        mock_tool.parameters_json_schema = {"type": "object"}
        mock_tool.function = AsyncMock()

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.mcp_integration"):
            create_mcp_server_from_tools(
                name="test_server", toolsets=[mock_tool], version="2.0.0"
            )

        assert any(
            "create_mcp_server_from_tools" in record.message
            and "name=" in record.message
            and "test_server" in record.message
            and "version=" in record.message
            for record in caplog.records
        ), (
            f"Expected server creation log not found. Records: {[r.message for r in caplog.records]}"
        )


class TestLogHandlerConfiguration:
    """Tests for StreamHandler configuration."""

    @pytest.fixture(autouse=True)
    def _restore_modules(self, restore_modules: None) -> None:
        """Auto-use the shared restore_modules fixture."""

    def test_handler_added_when_env_var_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Handler is added when CLAUDECODE_MODEL_LOG_LEVEL is explicitly set."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Clear existing handlers on the logger
        logger = logging.getLogger("claudecode_model")
        logger.handlers.clear()

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "DEBUG")

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_no_handler_when_env_var_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No handler added when env var is not set (default behavior)."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Clear existing handlers on the logger
        logger = logging.getLogger("claudecode_model")
        logger.handlers.clear()

        monkeypatch.delenv("CLAUDECODE_MODEL_LOG_LEVEL", raising=False)

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert len(logger.handlers) == 0

    def test_handler_format_correct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handler uses correct format."""
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Clear existing handlers on the logger
        logger = logging.getLogger("claudecode_model")
        logger.handlers.clear()

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "INFO")

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert handler.formatter is not None
        # Check format string contains expected components
        format_str = handler.formatter._fmt
        assert format_str is not None
        assert "%(asctime)s" in format_str
        assert "%(name)s" in format_str
        assert "%(levelname)s" in format_str
        assert "%(message)s" in format_str

    def test_no_duplicate_handlers_on_reimport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple imports don't add duplicate handlers."""
        import importlib
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Clear existing handlers on the logger
        logger = logging.getLogger("claudecode_model")
        logger.handlers.clear()

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "DEBUG")

        import claudecode_model

        # Force reload to simulate multiple imports
        importlib.reload(claudecode_model)

        logger = logging.getLogger("claudecode_model")
        # Should still have only one handler
        assert len(logger.handlers) == 1

    def test_handler_added_when_env_var_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Handler is added when CLAUDECODE_MODEL_LOG_LEVEL is empty string.

        An empty string is considered "explicitly set" (not None), so a handler
        is added. The empty string is falsy, so it falls back to "WARNING" via
        the `(_log_level_env or "WARNING")` expression (no warning emitted).
        """
        import sys

        # Remove cached module to force re-import
        modules_to_remove = [
            key for key in sys.modules if key.startswith("claudecode_model")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Clear existing handlers on the logger
        logger = logging.getLogger("claudecode_model")
        logger.handlers.clear()

        monkeypatch.setenv("CLAUDECODE_MODEL_LOG_LEVEL", "")

        import claudecode_model  # noqa: F401

        logger = logging.getLogger("claudecode_model")
        # Handler should be added because env var was explicitly set (even if empty)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        # Level should be WARNING (empty string is falsy, falls back to WARNING)
        assert logger.level == logging.WARNING


class TestCLILogging:
    """Tests for debug logging in cli.py."""

    def test_build_command_logs_parameters(self, caplog: LogCaptureFixture) -> None:
        """Test that _build_command logs command parameters."""
        from claudecode_model.cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(
            model="test-cli-model",
            permission_mode="plan",
            max_turns=7,
        )

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.cli"):
            with patch.object(cli, "_find_cli", return_value="/usr/bin/claude"):
                cli._build_command("test prompt for logging")

        assert any(
            "_build_command" in record.message
            and "model=" in record.message
            and "test-cli-model" in record.message
            for record in caplog.records
        ), (
            f"Expected build command log not found. Records: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.anyio
    async def test_execute_logs_completion(self, caplog: LogCaptureFixture) -> None:
        """Test that execute logs completion information."""
        from claudecode_model.cli import ClaudeCodeCLI

        cli = ClaudeCodeCLI(model="test-model", timeout=60.0)

        mock_response = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 200,
            "duration_api_ms": 150,
            "num_turns": 3,
            "result": "test result content",
            "session_id": "cli-session",
            "total_cost_usd": 0.05,
            "usage": {
                "input_tokens": 300,
                "output_tokens": 150,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }

        with caplog.at_level(logging.DEBUG, logger="claudecode_model.cli"):
            with patch.object(cli, "_find_cli", return_value="/usr/bin/claude"):
                with patch("asyncio.create_subprocess_exec") as mock_exec:
                    import json

                    mock_process = AsyncMock()
                    mock_process.returncode = 0
                    mock_process.communicate.return_value = (
                        json.dumps(mock_response).encode("utf-8"),
                        b"",
                    )
                    mock_exec.return_value = mock_process

                    await cli.execute("test prompt")

        assert any(
            "execute completed" in record.message
            and "duration_ms=" in record.message
            and "num_turns=" in record.message
            for record in caplog.records
        ), (
            f"Expected execute completion log not found. Records: {[r.message for r in caplog.records]}"
        )
