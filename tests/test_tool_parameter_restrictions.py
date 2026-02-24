"""Tests for tool_parameter_restrictions feature.

Verifies that ClaudeCodeModel can enforce parameter-level restrictions
on built-in tools (e.g., blocking Bash run_in_background=True) via
the SDK's can_use_tool callback mechanism.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from claudecode_model.model import ClaudeCodeModel


class TestBuildCanUseTool:
    """Tests for _build_can_use_tool() method."""

    def test_returns_none_when_no_restrictions(self) -> None:
        """No restrictions → no callback needed."""
        model = ClaudeCodeModel()
        assert model._build_can_use_tool() is None

    def test_returns_none_when_restrictions_empty(self) -> None:
        """Empty dict → no callback needed."""
        model = ClaudeCodeModel(tool_parameter_restrictions={})
        assert model._build_can_use_tool() is None

    def test_returns_callback_when_restrictions_set(self) -> None:
        """Non-empty restrictions → returns async callback."""
        model = ClaudeCodeModel(
            tool_parameter_restrictions={"Bash": {"run_in_background": False}}
        )
        callback = model._build_can_use_tool()
        assert callback is not None
        assert callable(callback)


class TestCanUseToolCallback:
    """Tests for the can_use_tool callback behavior."""

    @pytest.fixture()
    def model_with_bash_restriction(self) -> ClaudeCodeModel:
        """Model that restricts Bash run_in_background to False."""
        return ClaudeCodeModel(
            tool_parameter_restrictions={"Bash": {"run_in_background": False}}
        )

    @pytest.fixture()
    def context(self) -> ToolPermissionContext:
        """Default ToolPermissionContext for tests."""
        return ToolPermissionContext()

    @pytest.mark.anyio()
    async def test_denies_restricted_parameter_violation(
        self,
        model_with_bash_restriction: ClaudeCodeModel,
        context: ToolPermissionContext,
    ) -> None:
        """Bash with run_in_background=True should be denied."""
        callback = model_with_bash_restriction._build_can_use_tool()
        assert callback is not None

        result = await callback(
            "Bash",
            {"command": "sleep 100", "run_in_background": True},
            context,
        )
        assert isinstance(result, PermissionResultDeny)
        assert "run_in_background" in result.message

    @pytest.mark.anyio()
    async def test_allows_restricted_parameter_matching_value(
        self,
        model_with_bash_restriction: ClaudeCodeModel,
        context: ToolPermissionContext,
    ) -> None:
        """Bash with run_in_background=False should be allowed."""
        callback = model_with_bash_restriction._build_can_use_tool()
        assert callback is not None

        result = await callback(
            "Bash",
            {"command": "ls", "run_in_background": False},
            context,
        )
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.anyio()
    async def test_allows_when_restricted_parameter_absent(
        self,
        model_with_bash_restriction: ClaudeCodeModel,
        context: ToolPermissionContext,
    ) -> None:
        """Bash without run_in_background parameter should be allowed."""
        callback = model_with_bash_restriction._build_can_use_tool()
        assert callback is not None

        result = await callback(
            "Bash",
            {"command": "echo hello"},
            context,
        )
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.anyio()
    async def test_allows_unrestricted_tool(
        self,
        model_with_bash_restriction: ClaudeCodeModel,
        context: ToolPermissionContext,
    ) -> None:
        """Read tool (not restricted) should always be allowed."""
        callback = model_with_bash_restriction._build_can_use_tool()
        assert callback is not None

        result = await callback(
            "Read",
            {"file_path": "/etc/hosts"},
            context,
        )
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.anyio()
    async def test_multiple_tool_restrictions(
        self, context: ToolPermissionContext
    ) -> None:
        """Multiple tools with different restrictions."""
        model = ClaudeCodeModel(
            tool_parameter_restrictions={
                "Bash": {"run_in_background": False},
                "Write": {"create_directories": False},
            }
        )
        callback = model._build_can_use_tool()
        assert callback is not None

        # Bash violation
        result = await callback(
            "Bash",
            {"command": "sleep 100", "run_in_background": True},
            context,
        )
        assert isinstance(result, PermissionResultDeny)

        # Write violation
        result = await callback(
            "Write",
            {"file_path": "/tmp/test", "create_directories": True},
            context,
        )
        assert isinstance(result, PermissionResultDeny)

        # Bash OK
        result = await callback(
            "Bash",
            {"command": "ls"},
            context,
        )
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.anyio()
    async def test_multiple_parameters_per_tool(
        self, context: ToolPermissionContext
    ) -> None:
        """Multiple parameter restrictions on a single tool."""
        model = ClaudeCodeModel(
            tool_parameter_restrictions={
                "Bash": {
                    "run_in_background": False,
                    "dangerouslyDisableSandbox": False,
                },
            }
        )
        callback = model._build_can_use_tool()
        assert callback is not None

        # Violates run_in_background
        result = await callback(
            "Bash",
            {"command": "sleep 1", "run_in_background": True},
            context,
        )
        assert isinstance(result, PermissionResultDeny)
        assert "run_in_background" in result.message

        # Violates dangerouslyDisableSandbox
        result = await callback(
            "Bash",
            {"command": "rm -rf /", "dangerouslyDisableSandbox": True},
            context,
        )
        assert isinstance(result, PermissionResultDeny)
        assert "dangerouslyDisableSandbox" in result.message

        # Both compliant
        result = await callback(
            "Bash",
            {
                "command": "echo ok",
                "run_in_background": False,
                "dangerouslyDisableSandbox": False,
            },
            context,
        )
        assert isinstance(result, PermissionResultAllow)


class TestBuildAgentOptionsWithRestrictions:
    """Tests for _build_agent_options() integration with can_use_tool."""

    def test_no_can_use_tool_without_restrictions(self) -> None:
        """Agent options should not include can_use_tool when no restrictions."""
        model = ClaudeCodeModel()
        options = model._build_agent_options()
        assert options.can_use_tool is None

    def test_includes_can_use_tool_with_restrictions(self) -> None:
        """Agent options should include can_use_tool when restrictions are set."""
        model = ClaudeCodeModel(
            tool_parameter_restrictions={"Bash": {"run_in_background": False}}
        )
        options = model._build_agent_options()
        assert options.can_use_tool is not None
        assert callable(options.can_use_tool)


class TestToolParameterRestrictionsInit:
    """Tests for __init__ parameter handling."""

    def test_stores_restrictions(self) -> None:
        """Restrictions should be stored on the instance."""
        restrictions = {"Bash": {"run_in_background": False}}
        model = ClaudeCodeModel(tool_parameter_restrictions=restrictions)
        assert model._tool_parameter_restrictions == restrictions

    def test_default_is_none(self) -> None:
        """Default value for restrictions should be None."""
        model = ClaudeCodeModel()
        assert model._tool_parameter_restrictions is None

    def test_logged_in_debug(self) -> None:
        """Restrictions should appear in debug log."""
        with patch("claudecode_model.model.logger") as mock_logger:
            ClaudeCodeModel(
                tool_parameter_restrictions={"Bash": {"run_in_background": False}}
            )
            # Verify debug was called with a message that includes restrictions info
            mock_logger.debug.assert_called()
            call_args = mock_logger.debug.call_args
            assert "tool_parameter_restrictions" in call_args[0][0]
