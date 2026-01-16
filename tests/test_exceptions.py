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
        assert error.error_type is None
        assert error.recoverable is False

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

    def test_stores_error_type(self) -> None:
        """CLIExecutionError should store error_type."""
        error = CLIExecutionError("timeout", error_type="timeout")
        assert error.error_type == "timeout"

    def test_stores_recoverable(self) -> None:
        """CLIExecutionError should store recoverable flag."""
        error = CLIExecutionError("rate limited", recoverable=True)
        assert error.recoverable is True

    def test_stores_all_structured_attributes(self) -> None:
        """CLIExecutionError should store all structured error attributes."""
        error = CLIExecutionError(
            "Rate limit exceeded",
            exit_code=1,
            stderr="rate limit error",
            error_type="rate_limit",
            recoverable=True,
        )
        assert str(error) == "Rate limit exceeded"
        assert error.exit_code == 1
        assert error.stderr == "rate limit error"
        assert error.error_type == "rate_limit"
        assert error.recoverable is True

    def test_timeout_error_type(self) -> None:
        """CLIExecutionError should support timeout error type."""
        error = CLIExecutionError(
            "CLI execution timed out",
            exit_code=-9,
            stderr="Process was killed due to timeout",
            error_type="timeout",
            recoverable=True,
        )
        assert error.error_type == "timeout"
        assert error.recoverable is True

    def test_permission_error_type(self) -> None:
        """CLIExecutionError should support permission error type."""
        error = CLIExecutionError(
            "Permission denied",
            error_type="permission",
            recoverable=False,
        )
        assert error.error_type == "permission"
        assert error.recoverable is False

    def test_cli_not_found_error_type(self) -> None:
        """CLIExecutionError should support cli_not_found error type."""
        error = CLIExecutionError(
            "CLI not found",
            exit_code=127,
            error_type="cli_not_found",
            recoverable=False,
        )
        assert error.error_type == "cli_not_found"
        assert error.recoverable is False

    def test_invalid_response_error_type(self) -> None:
        """CLIExecutionError should support invalid_response error type."""
        error = CLIExecutionError(
            "Invalid response",
            error_type="invalid_response",
            recoverable=False,
        )
        assert error.error_type == "invalid_response"
        assert error.recoverable is False

    def test_unknown_error_type(self) -> None:
        """CLIExecutionError should support unknown error type."""
        error = CLIExecutionError(
            "Unknown error occurred",
            exit_code=1,
            error_type="unknown",
            recoverable=False,
        )
        assert error.error_type == "unknown"
        assert error.recoverable is False

    def test_default_recoverable_is_false(self) -> None:
        """CLIExecutionError recoverable should default to False."""
        error = CLIExecutionError("error", error_type="timeout")
        assert error.recoverable is False


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
