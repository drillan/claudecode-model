"""Tests for claudecode_model.cli module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudecode_model.cli import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_PROMPT_LENGTH,
    ClaudeCodeCLI,
)
from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
)


class TestConstants:
    """Tests for module constants."""

    def test_default_model(self) -> None:
        """DEFAULT_MODEL should be set."""
        assert DEFAULT_MODEL == "claude-sonnet-4-5"

    def test_default_timeout(self) -> None:
        """DEFAULT_TIMEOUT_SECONDS should be set."""
        assert DEFAULT_TIMEOUT_SECONDS == 120.0

    def test_max_prompt_length(self) -> None:
        """MAX_PROMPT_LENGTH should be set."""
        assert MAX_PROMPT_LENGTH == 1_000_000


class TestClaudeCodeCLIInit:
    """Tests for ClaudeCodeCLI initialization."""

    def test_default_values(self) -> None:
        """ClaudeCodeCLI should use default values."""
        cli = ClaudeCodeCLI()
        assert cli.model == DEFAULT_MODEL
        assert cli.timeout == DEFAULT_TIMEOUT_SECONDS
        assert cli.working_directory is None
        assert cli.allowed_tools is None
        assert cli.disallowed_tools is None
        assert cli.permission_mode is None
        assert cli.system_prompt is None

    def test_custom_values(self) -> None:
        """ClaudeCodeCLI should accept custom values."""
        cli = ClaudeCodeCLI(
            model="claude-opus-4",
            working_directory="/tmp",
            timeout=60.0,
            allowed_tools=["Read", "Write"],
            disallowed_tools=["Bash"],
            permission_mode="bypassPermissions",
            system_prompt="You are a helpful assistant.",
        )
        assert cli.model == "claude-opus-4"
        assert cli.working_directory == "/tmp"
        assert cli.timeout == 60.0
        assert cli.allowed_tools == ["Read", "Write"]
        assert cli.disallowed_tools == ["Bash"]
        assert cli.permission_mode == "bypassPermissions"
        assert cli.system_prompt == "You are a helpful assistant."

    def test_new_options_default_to_none(self) -> None:
        """ClaudeCodeCLI new options should default to None."""
        cli = ClaudeCodeCLI()
        assert cli.max_budget_usd is None
        assert cli.append_system_prompt is None
        assert cli.max_turns is None

    def test_new_options_accept_values(self) -> None:
        """ClaudeCodeCLI should accept new option values."""
        cli = ClaudeCodeCLI(
            max_budget_usd=1.5,
            append_system_prompt="Be concise.",
        )
        assert cli.max_budget_usd == 1.5
        assert cli.append_system_prompt == "Be concise."

    def test_rejects_negative_max_budget_usd(self) -> None:
        """ClaudeCodeCLI should reject negative max_budget_usd."""
        with pytest.raises(ValueError, match="max_budget_usd must be non-negative"):
            ClaudeCodeCLI(max_budget_usd=-1.0)

    def test_accepts_zero_max_budget_usd(self) -> None:
        """ClaudeCodeCLI should accept zero max_budget_usd."""
        cli = ClaudeCodeCLI(max_budget_usd=0.0)
        assert cli.max_budget_usd == 0.0

    def test_accepts_integer_max_budget_usd(self) -> None:
        """ClaudeCodeCLI should accept integer max_budget_usd and convert to float."""
        cli = ClaudeCodeCLI(max_budget_usd=5)  # type: ignore[arg-type]
        assert cli.max_budget_usd == 5.0
        assert isinstance(cli.max_budget_usd, float)

    def test_accepts_empty_string_append_system_prompt(self) -> None:
        """ClaudeCodeCLI should accept empty string append_system_prompt."""
        cli = ClaudeCodeCLI(append_system_prompt="")
        assert cli.append_system_prompt == ""

    def test_max_turns_accept_positive_value(self) -> None:
        """ClaudeCodeCLI should accept positive max_turns."""
        cli = ClaudeCodeCLI(max_turns=5)
        assert cli.max_turns == 5

    def test_max_turns_rejects_zero(self) -> None:
        """ClaudeCodeCLI should reject zero max_turns."""
        with pytest.raises(ValueError, match="max_turns must be a positive integer"):
            ClaudeCodeCLI(max_turns=0)

    def test_max_turns_rejects_negative(self) -> None:
        """ClaudeCodeCLI should reject negative max_turns."""
        with pytest.raises(ValueError, match="max_turns must be a positive integer"):
            ClaudeCodeCLI(max_turns=-1)


class TestClaudeCodeCLIFindCLI:
    """Tests for ClaudeCodeCLI._find_cli method."""

    def test_finds_cli_in_path(self) -> None:
        """_find_cli should find claude in PATH."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            path = cli._find_cli()
            assert path == "/usr/bin/claude"

    def test_caches_cli_path(self) -> None:
        """_find_cli should cache the CLI path."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value="/usr/bin/claude") as mock_which:
            cli._find_cli()
            cli._find_cli()
            mock_which.assert_called_once()

    def test_raises_when_cli_not_found(self) -> None:
        """_find_cli should raise CLINotFoundError when not found."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value=None):
            with pytest.raises(CLINotFoundError, match="claude CLI not found"):
                cli._find_cli()


class TestClaudeCodeCLIBuildCommand:
    """Tests for ClaudeCodeCLI._build_command method."""

    def test_builds_basic_command(self) -> None:
        """_build_command should build a basic command."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("Hello")
            assert cmd[0] == "/usr/bin/claude"
            assert "-p" in cmd
            assert "--output-format" in cmd
            assert "json" in cmd
            assert "--model" in cmd
            assert DEFAULT_MODEL in cmd
            assert cmd[-1] == "Hello"

    def test_includes_permission_mode(self) -> None:
        """_build_command should include permission mode if set."""
        cli = ClaudeCodeCLI(permission_mode="bypassPermissions")
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--permission-mode" in cmd
            assert "bypassPermissions" in cmd

    def test_includes_allowed_tools(self) -> None:
        """_build_command should include allowed tools if set."""
        cli = ClaudeCodeCLI(allowed_tools=["Read", "Write"])
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--allowed-tools" in cmd
            assert "Read" in cmd
            assert "Write" in cmd

    def test_includes_disallowed_tools(self) -> None:
        """_build_command should include disallowed tools if set."""
        cli = ClaudeCodeCLI(disallowed_tools=["Bash"])
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--disallowed-tools" in cmd
            assert "Bash" in cmd

    def test_includes_system_prompt(self) -> None:
        """_build_command should include system prompt if set."""
        cli = ClaudeCodeCLI(system_prompt="Be helpful")
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--system-prompt" in cmd
            assert "Be helpful" in cmd

    def test_raises_on_empty_prompt(self) -> None:
        """_build_command should raise ValueError on empty prompt."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(ValueError, match="Prompt cannot be empty"):
                cli._build_command("")

    def test_raises_on_whitespace_prompt(self) -> None:
        """_build_command should raise ValueError on whitespace-only prompt."""
        cli = ClaudeCodeCLI()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(ValueError, match="Prompt cannot be empty"):
                cli._build_command("   ")

    def test_raises_on_too_long_prompt(self) -> None:
        """_build_command should raise ValueError on too long prompt."""
        cli = ClaudeCodeCLI()
        long_prompt = "x" * (MAX_PROMPT_LENGTH + 1)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(ValueError, match="exceeds maximum length"):
                cli._build_command(long_prompt)

    def test_includes_max_budget_usd(self) -> None:
        """_build_command should include max-budget-usd if set."""
        cli = ClaudeCodeCLI(max_budget_usd=1.5)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--max-budget-usd" in cmd
            assert "1.5" in cmd

    def test_includes_append_system_prompt(self) -> None:
        """_build_command should include append-system-prompt if set."""
        cli = ClaudeCodeCLI(append_system_prompt="Be concise")
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--append-system-prompt" in cmd
            assert "Be concise" in cmd

    def test_includes_max_turns(self) -> None:
        """_build_command should include max-turns if set."""
        cli = ClaudeCodeCLI(max_turns=5)
        with patch("shutil.which", return_value="/usr/bin/claude"):
            cmd = cli._build_command("test")
            assert "--max-turns" in cmd
            assert "5" in cmd


class TestClaudeCodeCLIExecute:
    """Tests for ClaudeCodeCLI.execute method."""

    @pytest.fixture
    def valid_response_json(self) -> str:
        """Return a valid CLI response JSON."""
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 1000,
                "duration_api_ms": 800,
                "num_turns": 1,
                "result": "Hello from Claude!",
                "session_id": "test-session",
                "total_cost_usd": 0.01,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            }
        )

    @pytest.mark.asyncio
    async def test_successful_execution(self, valid_response_json: str) -> None:
        """execute should return CLIResponse on success."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(valid_response_json.encode(), b"")
        )

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            response = await cli.execute("Hello")
            assert response.result == "Hello from Claude!"
            assert response.is_error is False

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self) -> None:
        """execute should kill process on timeout."""
        cli = ClaudeCodeCLI(timeout=0.1)

        mock_process = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIExecutionError, match="timed out") as exc_info:
                await cli.execute("Hello")
            mock_process.kill.assert_called_once()
            assert exc_info.value.error_type == "timeout"
            assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_file_not_found_error(self) -> None:
        """execute should raise CLINotFoundError on FileNotFoundError."""
        cli = ClaudeCodeCLI()

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            with pytest.raises(CLINotFoundError, match="not found"):
                await cli.execute("Hello")

    @pytest.mark.asyncio
    async def test_permission_error(self) -> None:
        """execute should raise CLIExecutionError on PermissionError."""
        cli = ClaudeCodeCLI()

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=PermissionError("permission denied"),
            ),
        ):
            with pytest.raises(
                CLIExecutionError, match="Permission denied"
            ) as exc_info:
                await cli.execute("Hello")
            assert exc_info.value.error_type == "permission"
            assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_os_error(self) -> None:
        """execute should raise CLIExecutionError on OSError."""
        cli = ClaudeCodeCLI()

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("os error"),
            ),
        ):
            with pytest.raises(CLIExecutionError, match="OS error") as exc_info:
                await cli.execute("Hello")
            assert exc_info.value.error_type == "unknown"
            assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_non_zero_exit_code(self) -> None:
        """execute should raise CLIExecutionError on non-zero exit code."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(
                CLIExecutionError, match="exited with code 1"
            ) as exc_info:
                await cli.execute("Hello")
            assert exc_info.value.error_type == "unknown"
            assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_invalid_json_response(self) -> None:
        """execute should raise CLIResponseParseError on invalid JSON."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"not json", b""))

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIResponseParseError, match="Failed to parse"):
                await cli.execute("Hello")

    @pytest.mark.asyncio
    async def test_unicode_decode_error(self) -> None:
        """execute should raise CLIResponseParseError on decode error."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.returncode = 0
        # Invalid UTF-8 bytes
        mock_process.communicate = AsyncMock(return_value=(b"\xff\xfe", b""))

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIResponseParseError, match="Failed to decode"):
                await cli.execute("Hello")

    @pytest.mark.asyncio
    async def test_is_error_flag_raises(self) -> None:
        """execute should raise CLIExecutionError when is_error is true."""
        cli = ClaudeCodeCLI()

        error_response = json.dumps(
            {
                "type": "result",
                "subtype": "error",
                "is_error": True,
                "duration_ms": 0,
                "duration_api_ms": 0,
                "num_turns": 0,
                "result": "API error occurred",
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            }
        )

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(error_response.encode(), b"")
        )

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(
                CLIExecutionError, match="CLI reported error"
            ) as exc_info:
                await cli.execute("Hello")
            assert exc_info.value.error_type == "invalid_response"
            assert exc_info.value.recoverable is False

    @pytest.mark.asyncio
    async def test_cancelled_error_cleanup(self) -> None:
        """execute should cleanup on CancelledError."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.CancelledError())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cli.execute("Hello")
            mock_process.kill.assert_called_once()
