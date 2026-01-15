"""Tests for claudecode_model.exceptions module."""

import pytest

from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
    ClaudeCodeError,
)


class TestClaudeCodeError:
    """Tests for ClaudeCodeError base exception."""

    def test_is_base_exception(self) -> None:
        """ClaudeCodeError should be a subclass of Exception."""
        assert issubclass(ClaudeCodeError, Exception)

    def test_can_be_raised_with_message(self) -> None:
        """ClaudeCodeError should be raisable with a message."""
        with pytest.raises(ClaudeCodeError, match="test message"):
            raise ClaudeCodeError("test message")

    def test_exception_hierarchy(self) -> None:
        """All custom exceptions should inherit from ClaudeCodeError."""
        assert issubclass(CLINotFoundError, ClaudeCodeError)
        assert issubclass(CLIExecutionError, ClaudeCodeError)
        assert issubclass(CLIResponseParseError, ClaudeCodeError)


class TestCLINotFoundError:
    """Tests for CLINotFoundError exception."""

    def test_can_be_raised_with_message(self) -> None:
        """CLINotFoundError should be raisable with a message."""
        with pytest.raises(CLINotFoundError, match="CLI not found"):
            raise CLINotFoundError("CLI not found")

    def test_inherits_from_base(self) -> None:
        """CLINotFoundError should be catchable as ClaudeCodeError."""
        with pytest.raises(ClaudeCodeError):
            raise CLINotFoundError("test")


class TestCLIExecutionError:
    """Tests for CLIExecutionError exception."""

    def test_can_be_raised_with_message_only(self) -> None:
        """CLIExecutionError should be raisable with just a message."""
        error = CLIExecutionError("execution failed")
        assert str(error) == "execution failed"
        assert error.exit_code is None
        assert error.stderr == ""

    def test_stores_exit_code(self) -> None:
        """CLIExecutionError should store exit code."""
        error = CLIExecutionError("failed", exit_code=1)
        assert error.exit_code == 1

    def test_stores_stderr(self) -> None:
        """CLIExecutionError should store stderr."""
        error = CLIExecutionError("failed", stderr="error output")
        assert error.stderr == "error output"

    def test_stores_all_attributes(self) -> None:
        """CLIExecutionError should store all provided attributes."""
        error = CLIExecutionError(
            "CLI exited with code 127",
            exit_code=127,
            stderr="command not found",
        )
        assert str(error) == "CLI exited with code 127"
        assert error.exit_code == 127
        assert error.stderr == "command not found"

    def test_inherits_from_base(self) -> None:
        """CLIExecutionError should be catchable as ClaudeCodeError."""
        with pytest.raises(ClaudeCodeError):
            raise CLIExecutionError("test")


class TestCLIResponseParseError:
    """Tests for CLIResponseParseError exception."""

    def test_can_be_raised_with_message_only(self) -> None:
        """CLIResponseParseError should be raisable with just a message."""
        error = CLIResponseParseError("parse failed")
        assert str(error) == "parse failed"
        assert error.raw_output == ""

    def test_stores_raw_output(self) -> None:
        """CLIResponseParseError should store raw output."""
        error = CLIResponseParseError("parse failed", raw_output="invalid json")
        assert error.raw_output == "invalid json"

    def test_stores_all_attributes(self) -> None:
        """CLIResponseParseError should store all provided attributes."""
        raw = '{"incomplete": '
        error = CLIResponseParseError(
            "Failed to parse JSON",
            raw_output=raw,
        )
        assert str(error) == "Failed to parse JSON"
        assert error.raw_output == raw

    def test_inherits_from_base(self) -> None:
        """CLIResponseParseError should be catchable as ClaudeCodeError."""
        with pytest.raises(ClaudeCodeError):
            raise CLIResponseParseError("test")
