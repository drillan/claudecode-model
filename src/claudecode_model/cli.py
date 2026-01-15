"""Claude Code CLI subprocess execution."""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import TYPE_CHECKING

from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
)
from claudecode_model.types import CLIResponse, parse_cli_response

if TYPE_CHECKING:
    pass


class ClaudeCodeCLI:
    """Execute Claude Code CLI as subprocess."""

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-5",
        working_directory: str | None = None,
        timeout: float = 120.0,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.working_directory = working_directory
        self.timeout = timeout
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.permission_mode = permission_mode
        self.system_prompt = system_prompt

        self._cli_path: str | None = None

    def _find_cli(self) -> str:
        """Find the claude CLI executable."""
        if self._cli_path is not None:
            return self._cli_path

        cli_path = shutil.which("claude")
        if cli_path is None:
            raise CLINotFoundError(
                "claude CLI not found. "
                "Please install Claude Code: https://claude.ai/download"
            )
        self._cli_path = cli_path
        return cli_path

    def _build_command(self, prompt: str) -> list[str]:
        """Build the CLI command with arguments."""
        cli_path = self._find_cli()
        cmd = [
            cli_path,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
        ]

        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])

        if self.allowed_tools:
            cmd.extend(["--allowed-tools", *self.allowed_tools])

        if self.disallowed_tools:
            cmd.extend(["--disallowed-tools", *self.disallowed_tools])

        if self.system_prompt:
            cmd.extend(["--system-prompt", self.system_prompt])

        cmd.append(prompt)
        return cmd

    async def execute(self, prompt: str) -> CLIResponse:
        """Execute the CLI with the given prompt and return the response."""
        cmd = self._build_command(prompt)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

        except asyncio.TimeoutError as e:
            raise CLIExecutionError(
                f"CLI execution timed out after {self.timeout} seconds",
                exit_code=None,
                stderr="",
            ) from e
        except FileNotFoundError as e:
            raise CLINotFoundError(f"claude CLI not found: {e}") from e

        stdout_str = stdout.decode("utf-8")
        stderr_str = stderr.decode("utf-8")

        if process.returncode != 0:
            raise CLIExecutionError(
                f"CLI exited with code {process.returncode}",
                exit_code=process.returncode,
                stderr=stderr_str,
            )

        try:
            data = json.loads(stdout_str)
        except json.JSONDecodeError as e:
            raise CLIResponseParseError(
                f"Failed to parse CLI JSON output: {e}",
                raw_output=stdout_str,
            ) from e

        return parse_cli_response(data)
