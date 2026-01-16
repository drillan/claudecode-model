"""Claude Code CLI subprocess execution."""

from __future__ import annotations

import asyncio
import json
import shutil

from claudecode_model.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIResponseParseError,
)
from claudecode_model.types import CLIResponse, CLIResponseData, parse_cli_response

# Constants
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_PROMPT_LENGTH = 1_000_000  # 1MB limit


class ClaudeCodeCLI:
    """Execute Claude Code CLI as subprocess."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        working_directory: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        system_prompt: str | None = None,
        max_budget_usd: float | None = None,
        append_system_prompt: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        if max_budget_usd is not None and max_budget_usd < 0:
            raise ValueError("max_budget_usd must be non-negative")

        if max_turns is not None and max_turns <= 0:
            raise ValueError("max_turns must be a positive integer")

        self.model = model
        self.working_directory = working_directory
        self.timeout = timeout
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.permission_mode = permission_mode
        self.system_prompt = system_prompt
        self.max_budget_usd = (
            float(max_budget_usd) if max_budget_usd is not None else None
        )
        self.append_system_prompt = append_system_prompt
        self.max_turns = max_turns

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
        """Build the CLI command with arguments.

        Args:
            prompt: The user prompt to send to the CLI.

        Returns:
            List of command arguments.

        Raises:
            ValueError: If prompt is empty or exceeds maximum length.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(
                f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters"
            )

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

        if self.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(self.max_budget_usd)])

        if self.append_system_prompt:
            cmd.extend(["--append-system-prompt", self.append_system_prompt])

        if self.max_turns is not None:
            cmd.extend(["--max-turns", str(self.max_turns)])

        cmd.append(prompt)
        return cmd

    async def execute(self, prompt: str) -> CLIResponse:
        """Execute the CLI with the given prompt and return the response.

        Args:
            prompt: The user prompt to send to the CLI.

        Returns:
            Parsed CLI response.

        Raises:
            CLINotFoundError: If the claude CLI is not found.
            CLIExecutionError: If CLI execution fails or returns an error.
            CLIResponseParseError: If the CLI output cannot be parsed.
            ValueError: If the prompt is invalid.
        """
        cmd = self._build_command(prompt)
        process: asyncio.subprocess.Process | None = None

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
            if process is not None:
                process.kill()
                await process.wait()
            raise CLIExecutionError(
                f"CLI execution timed out after {self.timeout} seconds. "
                "Consider increasing the timeout or simplifying the request.",
                exit_code=-9,
                stderr="Process was killed due to timeout",
                error_type="timeout",
                recoverable=True,
            ) from e
        except asyncio.CancelledError:
            if process is not None:
                process.kill()
                await process.wait()
            raise
        except FileNotFoundError as e:
            raise CLINotFoundError(
                f"claude CLI not found at expected location. "
                f"Please install Claude Code: https://claude.ai/download. "
                f"Details: {e}"
            ) from e
        except PermissionError as e:
            raise CLIExecutionError(
                f"Permission denied when executing claude CLI. "
                f"Check file permissions: {e}",
                exit_code=None,
                stderr=str(e),
                error_type="permission",
                recoverable=False,
            ) from e
        except OSError as e:
            raise CLIExecutionError(
                f"OS error during CLI execution: {e}. "
                f"Working directory: {self.working_directory}",
                exit_code=None,
                stderr=str(e),
                error_type="unknown",
                recoverable=False,
            ) from e

        try:
            stdout_str = stdout.decode("utf-8")
            stderr_str = stderr.decode("utf-8")
        except UnicodeDecodeError as e:
            raise CLIResponseParseError(
                f"Failed to decode CLI output as UTF-8: {e}",
                raw_output=repr(stdout[:500]),
            ) from e

        if process.returncode != 0:
            raise CLIExecutionError(
                f"CLI exited with code {process.returncode}",
                exit_code=process.returncode,
                stderr=stderr_str,
                error_type="unknown",
                recoverable=False,
            )

        try:
            data: CLIResponseData = json.loads(stdout_str)
        except json.JSONDecodeError as e:
            raise CLIResponseParseError(
                f"Failed to parse CLI JSON output: {e}",
                raw_output=stdout_str,
            ) from e

        response = parse_cli_response(data)

        if response.is_error:
            raise CLIExecutionError(
                f"CLI reported error: {response.result or 'Unknown error'}",
                exit_code=process.returncode,
                stderr=response.result,
                error_type="invalid_response",
                recoverable=False,
            )

        return response
