"""Tests for graceful exit and interrupt handling (Issue #106)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudecode_model.cli import ClaudeCodeCLI
from claudecode_model.exceptions import CLIInterruptedError


# ============================================================
# CLIInterruptedError exception tests
# ============================================================


class TestCLIInterruptedError:
    """Tests for CLIInterruptedError exception."""

    def test_basic_creation(self) -> None:
        """CLIInterruptedError should be created with a message."""
        err = CLIInterruptedError("User interrupted")
        assert str(err) == "User interrupted"

    def test_inherits_from_claude_code_error(self) -> None:
        """CLIInterruptedError should inherit from ClaudeCodeError."""
        from claudecode_model.exceptions import ClaudeCodeError

        err = CLIInterruptedError("interrupted")
        assert isinstance(err, ClaudeCodeError)

    def test_is_exported(self) -> None:
        """CLIInterruptedError should be exported from the package."""
        from claudecode_model import CLIInterruptedError as exported

        assert exported is CLIInterruptedError


# ============================================================
# Graceful process termination tests (cli.py)
# ============================================================


class TestGracefulTermination:
    """Tests for graceful subprocess termination on KeyboardInterrupt."""

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_sends_sigterm_first(self) -> None:
        """On KeyboardInterrupt, SIGTERM should be sent before SIGKILL."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=KeyboardInterrupt())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIInterruptedError):
                await cli.execute("Hello")
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_falls_back_to_sigkill(self) -> None:
        """If SIGTERM doesn't stop the process, SIGKILL should be used."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        # First wait (after SIGTERM) times out, second wait (after SIGKILL) succeeds
        mock_process.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None])
        mock_process.communicate = AsyncMock(side_effect=KeyboardInterrupt())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIInterruptedError):
                await cli.execute("Hello")
            mock_process.terminate.assert_called_once()
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_process_exits_on_sigterm(self) -> None:
        """If process exits on SIGTERM, SIGKILL should not be sent."""
        cli = ClaudeCodeCLI()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        # wait returns immediately (process exited after SIGTERM)
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.communicate = AsyncMock(side_effect=KeyboardInterrupt())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIInterruptedError):
                await cli.execute("Hello")
            mock_process.terminate.assert_called_once()
            mock_process.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_no_process(self) -> None:
        """KeyboardInterrupt before process creation should raise CLIInterruptedError."""
        cli = ClaudeCodeCLI()

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=KeyboardInterrupt(),
            ),
        ):
            with pytest.raises(CLIInterruptedError):
                await cli.execute("Hello")


# ============================================================
# Interrupt handler callback tests
# ============================================================


class TestInterruptHandler:
    """Tests for interrupt_handler callback parameter."""

    def test_init_with_interrupt_handler(self) -> None:
        """ClaudeCodeCLI should accept interrupt_handler parameter."""
        handler = MagicMock(return_value=True)
        cli = ClaudeCodeCLI(interrupt_handler=handler)
        assert cli.interrupt_handler is handler

    def test_init_default_interrupt_handler_is_none(self) -> None:
        """Default interrupt_handler should be None."""
        cli = ClaudeCodeCLI()
        assert cli.interrupt_handler is None

    @pytest.mark.asyncio
    async def test_interrupt_handler_called_on_keyboard_interrupt(self) -> None:
        """interrupt_handler should be called when KeyboardInterrupt occurs."""
        handler = MagicMock(return_value=True)
        cli = ClaudeCodeCLI(interrupt_handler=handler)

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.communicate = AsyncMock(side_effect=KeyboardInterrupt())

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            with pytest.raises(CLIInterruptedError):
                await cli.execute("Hello")
            handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_interrupt_handler_returns_false_continues(self) -> None:
        """If interrupt_handler returns False, execution should continue."""
        import json as json_mod

        handler = MagicMock(return_value=False)
        cli = ClaudeCodeCLI(interrupt_handler=handler)

        valid_response = json_mod.dumps(
            {
                "type": "result",
                "subtype": "success",
                "result": "hello",
                "is_error": False,
                "duration_ms": 100,
                "duration_api_ms": 80,
                "num_turns": 1,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "session_id": "test-session",
            }
        ).encode()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        # First call raises KeyboardInterrupt, second call returns normally
        mock_process.communicate = AsyncMock(
            side_effect=[
                KeyboardInterrupt(),
                (valid_response, b""),
            ]
        )

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
        ):
            result = await cli.execute("Hello")
            assert result.result == "hello"
            handler.assert_called_once()
            mock_process.terminate.assert_not_called()


# ============================================================
# Graceful termination timeout constant test
# ============================================================


class TestGracefulTerminationConstants:
    """Tests for graceful termination constants."""

    def test_graceful_termination_timeout_exists(self) -> None:
        """GRACEFUL_TERMINATION_TIMEOUT_SECONDS should be defined."""
        from claudecode_model.cli import GRACEFUL_TERMINATION_TIMEOUT_SECONDS

        assert isinstance(GRACEFUL_TERMINATION_TIMEOUT_SECONDS, (int, float))
        assert GRACEFUL_TERMINATION_TIMEOUT_SECONDS > 0

    def test_graceful_termination_timeout_value(self) -> None:
        """GRACEFUL_TERMINATION_TIMEOUT_SECONDS should be 5 seconds."""
        from claudecode_model.cli import GRACEFUL_TERMINATION_TIMEOUT_SECONDS

        assert GRACEFUL_TERMINATION_TIMEOUT_SECONDS == 5.0


# ============================================================
# Model-level interrupt handling tests
# ============================================================


class TestModelInterruptHandling:
    """Tests for interrupt handling in ClaudeCodeModel."""

    @pytest.mark.asyncio
    async def test_model_init_with_interrupt_handler(self) -> None:
        """ClaudeCodeModel should accept interrupt_handler parameter."""
        from claudecode_model.model import ClaudeCodeModel

        handler = MagicMock(return_value=True)
        model = ClaudeCodeModel(interrupt_handler=handler)
        assert model._interrupt_handler is handler

    @pytest.mark.asyncio
    async def test_model_default_interrupt_handler_is_none(self) -> None:
        """Default interrupt_handler should be None."""
        from claudecode_model.model import ClaudeCodeModel

        model = ClaudeCodeModel()
        assert model._interrupt_handler is None
