"""pydantic-ai Model implementation using Claude Agent SDK."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from functools import cached_property
from typing import TYPE_CHECKING

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.profiles import ModelProfile

from claudecode_model.cli import (
    DEFAULT_MAX_TURNS_WITH_JSON_SCHEMA,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    TIMEOUT_EXIT_CODE,
)
from claudecode_model.exceptions import (
    CLIExecutionError,
    StructuredOutputError,
    ToolNotFoundError,
    ToolsetNotRegisteredError,
)
from claudecode_model.mcp_integration import (
    MCP_SERVER_NAME,
    AgentToolset,
    PydanticAITool,
    create_mcp_server_from_tools,
)
from claudecode_model.types import (
    CLIResponse,
    CLIUsage,
    JsonValue,
    RequestWithMetadataResult,
)

if TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.tools import ToolDefinition

logger = logging.getLogger(__name__)


class ClaudeCodeModel(Model):
    """pydantic-ai Model implementation using Claude Agent SDK."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        working_directory: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self._model_name = model_name
        self._working_directory = working_directory
        self._timeout = timeout
        self._allowed_tools = allowed_tools
        self._disallowed_tools = disallowed_tools
        self._permission_mode = permission_mode
        self._max_turns = max_turns
        self._mcp_servers: dict[str, McpSdkServerConfig] = {}
        self._agent_toolsets: Sequence[PydanticAITool] | AgentToolset | None = None
        self._tools_cache: dict[str, PydanticAITool] = {}

        logger.debug(
            "ClaudeCodeModel initialized: model=%s, working_directory=%s, "
            "timeout=%s, allowed_tools=%s, disallowed_tools=%s, "
            "permission_mode=%s, max_turns=%s",
            self._model_name,
            self._working_directory,
            self._timeout,
            self._allowed_tools,
            self._disallowed_tools,
            self._permission_mode,
            self._max_turns,
        )

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def system(self) -> str:
        """Return the system identifier for OpenTelemetry."""
        return "claude-code"

    @cached_property
    def profile(self) -> ModelProfile:
        """Return model profile with JSON schema output support.

        Claude Code CLI supports --json-schema option for structured output,
        so we enable supports_json_schema_output and set default_structured_output_mode
        to 'native' to leverage this capability.
        """
        return ModelProfile(
            supports_json_schema_output=True,
            default_structured_output_mode="native",
        )

    def _extract_system_prompt(self, messages: list[ModelMessage]) -> str | None:
        """Extract system prompt from messages."""
        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, SystemPromptPart):
                        return part.content
        return None

    def _extract_user_prompt(self, messages: list[ModelMessage]) -> str:
        """Extract user prompt from the last message.

        Args:
            messages: List of conversation messages.

        Returns:
            Concatenated user prompt string.

        Raises:
            ValueError: If no user prompt is found in messages.
        """
        parts: list[str] = []

        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        content = part.content
                        if isinstance(content, str):
                            parts.append(content)
                        elif isinstance(content, Iterable) and not isinstance(
                            content, (str, bytes)
                        ):
                            for item in content:
                                if isinstance(item, str):
                                    parts.append(item)

        if not parts:
            raise ValueError(
                "No user prompt found in messages. "
                "Ensure at least one UserPromptPart with string content is provided."
            )

        return "\n".join(parts)

    def _extract_json_schema(
        self, model_request_parameters: ModelRequestParameters
    ) -> dict[str, JsonValue] | None:
        """Extract JSON schema from model request parameters.

        Args:
            model_request_parameters: Request parameters for tools and output.

        Returns:
            JSON schema dict if effective output_mode is 'native' and output_object is set,
            None otherwise.

        Note:
            When output_mode is 'auto', resolves to profile.default_structured_output_mode.
        """
        output_mode = model_request_parameters.output_mode

        # Resolve 'auto' mode using profile's default
        if output_mode == "auto":
            output_mode = self.profile.default_structured_output_mode

        if output_mode == "native":
            if model_request_parameters.output_object is not None:
                return model_request_parameters.output_object.json_schema
        return None

    def _build_agent_options(
        self,
        system_prompt: str | None = None,
        append_system_prompt: str | None = None,
        max_budget_usd: float | None = None,
        max_turns: int | None = None,
        working_directory: str | None = None,
        json_schema: dict[str, JsonValue] | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from current parameters.

        Args:
            system_prompt: System prompt to include.
            append_system_prompt: Additional system prompt to append.
            max_budget_usd: Maximum budget in USD.
            max_turns: Maximum number of turns.
            working_directory: Working directory for execution.
            json_schema: JSON schema for structured output.

        Returns:
            ClaudeAgentOptions configured with the provided parameters.
        """
        # Handle append_system_prompt
        effective_system_prompt = system_prompt
        if append_system_prompt:
            if effective_system_prompt:
                effective_system_prompt = (
                    f"{effective_system_prompt}\n\n{append_system_prompt}"
                )
            else:
                effective_system_prompt = append_system_prompt

        # Build output_format if json_schema is provided
        output_format: dict[str, JsonValue] | None = None
        if json_schema is not None:
            output_format = {"type": "json_schema", "schema": json_schema}

        # Use provided values or fall back to instance defaults
        effective_max_turns = max_turns if max_turns is not None else self._max_turns
        effective_cwd = (
            working_directory
            if working_directory is not None
            else self._working_directory
        )

        return ClaudeAgentOptions(
            model=self._model_name,
            cwd=effective_cwd,
            allowed_tools=self._allowed_tools or [],
            disallowed_tools=self._disallowed_tools or [],
            permission_mode=self._permission_mode,  # type: ignore[arg-type]
            max_turns=effective_max_turns,
            max_budget_usd=max_budget_usd,
            system_prompt=effective_system_prompt,
            output_format=output_format,
            mcp_servers=self._mcp_servers,  # type: ignore[arg-type]
        )

    async def _execute_sdk_query(
        self,
        prompt: str,
        options: ClaudeAgentOptions,
        timeout: float,
    ) -> ResultMessage:
        """Execute Claude Agent SDK query and return ResultMessage.

        Args:
            prompt: The user prompt to send.
            options: ClaudeAgentOptions for the query.
            timeout: Timeout in seconds.

        Returns:
            ResultMessage from the SDK.

        Raises:
            CLIExecutionError: If timeout occurs or no ResultMessage is received.
        """
        logger.debug(
            "_execute_sdk_query started: prompt_length=%d, timeout=%s, "
            "model=%s, max_turns=%s",
            len(prompt),
            timeout,
            options.model,
            options.max_turns,
        )

        result_message: ResultMessage | None = None

        async def run_query() -> ResultMessage:
            nonlocal result_message
            try:
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, ResultMessage):
                        result_message = message
            except Exception as e:
                raise CLIExecutionError(
                    f"SDK query failed: {e}",
                    exit_code=None,
                    stderr=str(e),
                    error_type="unknown",
                    recoverable=False,
                ) from e
            if result_message is None:
                raise CLIExecutionError(
                    "No ResultMessage received from SDK",
                    exit_code=None,
                    stderr="Query completed but no ResultMessage was yielded",
                    error_type="invalid_response",
                    recoverable=False,
                )
            return result_message

        # Use anyio.move_on_after for timeout handling
        with anyio.move_on_after(timeout) as cancel_scope:
            result = await run_query()
            logger.debug(
                "_execute_sdk_query completed: num_turns=%s, duration_ms=%s, "
                "is_error=%s, input_tokens=%d, output_tokens=%d",
                result.num_turns,
                result.duration_ms,
                result.is_error,
                result.usage.get("input_tokens", 0) if result.usage else 0,
                result.usage.get("output_tokens", 0) if result.usage else 0,
            )
            return result

        if cancel_scope.cancelled_caught:
            raise CLIExecutionError(
                f"SDK query timed out after {timeout} seconds",
                exit_code=TIMEOUT_EXIT_CODE,
                stderr="Query was cancelled due to timeout",
                error_type="timeout",
                recoverable=True,
            )

        # This should never be reached, but satisfy type checker
        raise CLIExecutionError(  # pragma: no cover
            "Unexpected state in _execute_sdk_query",
            exit_code=None,
            stderr="",
            error_type="unknown",
            recoverable=False,
        )

    def _try_unwrap_parameters_wrapper(
        self, result: ResultMessage
    ) -> dict[str, JsonValue] | None:
        """Try to unwrap {"parameters": {...}} format from result string.

        Some models wrap structured output in a parameters envelope. This method
        detects and unwraps this format when structured_output is not already set.

        Args:
            result: ResultMessage from Claude Agent SDK.

        Returns:
            Unwrapped dict if parameters wrapper detected, None otherwise.
        """
        # Only process if structured_output is not already set
        if result.structured_output is not None:
            return None

        # Only process if result is a non-empty string
        if not result.result:
            return None

        # Try to parse as JSON
        try:
            parsed = json.loads(result.result)
        except (json.JSONDecodeError, TypeError):
            return None

        # Check for {"parameters": {...}} format (single key)
        if not isinstance(parsed, dict):
            return None

        if list(parsed.keys()) != ["parameters"]:
            return None

        parameters_value = parsed["parameters"]
        if not isinstance(parameters_value, dict):
            return None

        # Log warning about automatic unwrapping
        logger.warning(
            "Detected and unwrapped parameters wrapper in result. "
            "session_id=%s, num_turns=%s",
            result.session_id,
            result.num_turns,
        )

        return parameters_value

    def _result_message_to_cli_response(self, result: ResultMessage) -> CLIResponse:
        """Convert ResultMessage to CLIResponse.

        CLIResponse provides detailed metadata (model_usage, permission_denials, etc.)
        that is exposed via RequestWithMetadataResult API.

        Args:
            result: ResultMessage from Claude Agent SDK.

        Returns:
            CLIResponse with equivalent data.
        """
        # Log warning before CLIResponse validation fails,
        # so debug info appears even if exception is caught
        if not result.result and result.structured_output is None:
            logger.warning(
                "ResultMessage has empty result and no structured_output. "
                "is_error=%s, num_turns=%s, duration_ms=%s, subtype=%s",
                result.is_error,
                result.num_turns,
                result.duration_ms,
                result.subtype,
            )

        usage_data = result.usage
        if usage_data is None:
            logger.warning(
                "ResultMessage.usage is None, using default values of 0 for all usage fields"
            )
            usage_data = {}

        # Try to unwrap parameters wrapper if structured_output is not set
        structured_output = result.structured_output
        if structured_output is None:
            unwrapped = self._try_unwrap_parameters_wrapper(result)
            if unwrapped is not None:
                structured_output = unwrapped

        return CLIResponse(
            type="result",
            subtype=result.subtype,
            is_error=result.is_error,
            duration_ms=result.duration_ms,
            duration_api_ms=result.duration_api_ms,
            num_turns=result.num_turns,
            result=result.result or "",
            session_id=result.session_id,
            total_cost_usd=result.total_cost_usd,
            usage=CLIUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                cache_creation_input_tokens=usage_data.get(
                    "cache_creation_input_tokens", 0
                ),
                cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
            ),
            structured_output=structured_output,
        )

    async def _execute_request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        json_schema: dict[str, JsonValue] | None = None,
    ) -> CLIResponse:
        """Execute SDK request and return raw response.

        Internal method that handles the actual SDK execution logic.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).
            json_schema: Optional JSON schema for structured output.

        Returns:
            CLIResponse containing the response with all metadata.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLIExecutionError: If SDK execution fails or times out.
        """
        logger.debug(
            "_execute_request started: num_messages=%d, has_model_settings=%s, "
            "has_json_schema=%s",
            len(messages),
            model_settings is not None,
            json_schema is not None,
        )

        system_prompt = self._extract_system_prompt(messages)
        user_prompt = self._extract_user_prompt(messages)

        # Extract settings from model_settings
        timeout = self._timeout
        max_budget_usd: float | None = None
        append_system_prompt: str | None = None
        max_turns: int | None = self._max_turns
        working_directory: str | None = self._working_directory

        if model_settings is not None:
            timeout_value = model_settings.get("timeout")
            if timeout_value is not None:
                if isinstance(timeout_value, (int, float)):
                    timeout = float(timeout_value)
                else:
                    logger.warning(
                        "model_settings 'timeout' has invalid type %s, "
                        "expected int or float. Using default timeout.",
                        type(timeout_value).__name__,
                    )

            max_budget_value = model_settings.get("max_budget_usd")
            if max_budget_value is not None:
                if isinstance(max_budget_value, (int, float)):
                    max_budget_usd = float(max_budget_value)
                    if max_budget_usd < 0:
                        raise ValueError("max_budget_usd must be non-negative")
                else:
                    logger.warning(
                        "model_settings 'max_budget_usd' has invalid type %s, "
                        "expected int or float. Ignoring this setting.",
                        type(max_budget_value).__name__,
                    )

            append_prompt_value = model_settings.get("append_system_prompt")
            if append_prompt_value is not None:
                if isinstance(append_prompt_value, str):
                    append_system_prompt = append_prompt_value
                else:
                    logger.warning(
                        "model_settings 'append_system_prompt' has invalid type %s, "
                        "expected str. Ignoring this setting.",
                        type(append_prompt_value).__name__,
                    )

            max_turns_value = model_settings.get("max_turns")
            if max_turns_value is not None:
                if isinstance(max_turns_value, int) and not isinstance(
                    max_turns_value, bool
                ):
                    if max_turns_value <= 0:
                        raise ValueError("max_turns must be a positive integer")
                    max_turns = max_turns_value
                else:
                    logger.warning(
                        "model_settings 'max_turns' has invalid type %s, "
                        "expected int. Ignoring this setting.",
                        type(max_turns_value).__name__,
                    )

            wd_value = model_settings.get("working_directory")
            if wd_value is not None:
                if not isinstance(wd_value, str):
                    raise TypeError(
                        f"model_settings 'working_directory' must be str, "
                        f"got {type(wd_value).__name__}"
                    )
                if wd_value == "":
                    logger.warning(
                        "model_settings 'working_directory' is an empty string. "
                        "This may not be a valid path."
                    )
                working_directory = wd_value

        # Apply default max_turns for json_schema mode
        effective_max_turns = max_turns
        if json_schema is not None and effective_max_turns is None:
            effective_max_turns = DEFAULT_MAX_TURNS_WITH_JSON_SCHEMA

        # Build ClaudeAgentOptions
        options = self._build_agent_options(
            system_prompt=system_prompt,
            append_system_prompt=append_system_prompt,
            max_budget_usd=max_budget_usd,
            max_turns=effective_max_turns,
            working_directory=working_directory,
            json_schema=json_schema,
        )

        # Execute SDK query
        result = await self._execute_sdk_query(user_prompt, options, timeout)

        # Check for error response from SDK
        if result.is_error:
            raise CLIExecutionError(
                f"SDK reported error: {result.result or 'Unknown error'}",
                exit_code=None,
                stderr=result.result or "",
                error_type="invalid_response",
                recoverable=False,
            )

        # Check for structured output extraction failure
        if result.subtype == "error_max_structured_output_retries":
            logger.error(
                "Structured output failed after maximum retries: "
                "session_id=%s, num_turns=%s, duration_ms=%s. "
                "Debug session file: ~/.claude/projects/<project-hash>/%s.jsonl",
                result.session_id,
                result.num_turns,
                result.duration_ms,
                result.session_id,
            )
            raise StructuredOutputError(
                f"Structured output failed after maximum retries. "
                f"The model returned output that did not match the required schema. "
                f"Session: {result.session_id}, Turns: {result.num_turns}, "
                f"Duration: {result.duration_ms}ms",
                session_id=result.session_id,
                num_turns=result.num_turns,
                duration_ms=result.duration_ms,
            )

        # Warn about unknown error subtypes for future SDK compatibility
        if (
            result.subtype
            and result.subtype.startswith("error_")
            and not result.is_error
        ):
            logger.warning(
                "Unknown error subtype encountered: %s (session_id=%s)",
                result.subtype,
                result.session_id,
            )

        # Convert to CLIResponse which provides detailed metadata for public API
        cli_response = self._result_message_to_cli_response(result)

        logger.debug(
            "_execute_request completed: duration_ms=%s, num_turns=%s, "
            "has_structured_output=%s",
            cli_response.duration_ms,
            cli_response.num_turns,
            cli_response.structured_output is not None,
        )

        return cli_response

    def _process_function_tools(
        self,
        function_tools: list[ToolDefinition],
    ) -> None:
        """Process function_tools and update MCP server if needed.

        Args:
            function_tools: List of ToolDefinition from model_request_parameters.

        Raises:
            ToolsetNotRegisteredError: If function_tools are provided but no
                toolsets are registered via set_agent_toolsets().
            ToolNotFoundError: If some of the requested tools are not found
                in the registered toolsets.

        Side Effects:
            Updates self._mcp_servers with a new MCP server containing only
            the matched tools from function_tools.
        """
        if not function_tools:
            return

        tool_names = [td.name for td in function_tools]

        logger.debug(
            "_process_function_tools: num_tools=%d, tool_names=%s",
            len(tool_names),
            tool_names,
        )

        # Check if toolsets are registered
        if self._agent_toolsets is None:
            raise ToolsetNotRegisteredError(requested_tools=tool_names)

        # Find matching tools by name
        matched_tools, missing_tools = self._find_tools_by_names(tool_names)

        if missing_tools:
            available_tools = self._get_available_tool_names()
            raise ToolNotFoundError(
                missing_tools=missing_tools, available_tools=available_tools
            )

        if matched_tools:
            # Update MCP server with matched tools only
            self._mcp_servers[MCP_SERVER_NAME] = create_mcp_server_from_tools(
                name=MCP_SERVER_NAME,
                toolsets=matched_tools,
            )

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request to Claude Agent SDK.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).
            model_request_parameters: Request parameters for tools and output.

        Returns:
            ModelResponse containing the SDK response.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLIExecutionError: If SDK execution fails or times out.
        """
        # Process function_tools to update MCP server
        self._process_function_tools(model_request_parameters.function_tools)

        json_schema = self._extract_json_schema(model_request_parameters)
        cli_response = await self._execute_request(
            messages, model_settings, json_schema=json_schema
        )
        return cli_response.to_model_response(model_name=self._model_name)

    async def request_with_metadata(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> RequestWithMetadataResult:
        """Make a request to Claude Agent SDK and return both response and metadata.

        This method is useful when you need access to SDK metadata such as
        total_cost_usd, duration_api_ms, num_turns, etc., which are lost
        during the to_model_response() conversion.

        Args:
            messages: The conversation messages.
            model_settings: Optional model settings (timeout, max_budget_usd, max_turns, append_system_prompt, working_directory).
            model_request_parameters: Request parameters for tools and output.

        Returns:
            RequestWithMetadataResult containing:
                - response: ModelResponse for use with pydantic-ai Agent.
                - cli_response: Raw CLIResponse with full metadata.

        Raises:
            ValueError: If no user prompt is found in messages.
            CLIExecutionError: If SDK execution fails or times out.

        Example:
            ```python
            model = ClaudeCodeModel()
            result = await model.request_with_metadata(messages, settings, params)
            metadata = {
                "total_cost_usd": result.cli_response.total_cost_usd,
                "num_turns": result.cli_response.num_turns,
                "duration_api_ms": result.cli_response.duration_api_ms,
            }
            ```
        """
        # Process function_tools to update MCP server
        self._process_function_tools(model_request_parameters.function_tools)

        json_schema = self._extract_json_schema(model_request_parameters)
        cli_response = await self._execute_request(
            messages, model_settings, json_schema=json_schema
        )
        return RequestWithMetadataResult(
            response=cli_response.to_model_response(model_name=self._model_name),
            cli_response=cli_response,
        )

    def set_agent_toolsets(
        self, toolsets: Sequence[PydanticAITool] | AgentToolset | None
    ) -> None:
        """Register pydantic-ai Agent toolsets for MCP server exposure.

        Converts pydantic-ai tools to an MCP server that can be used by Claude.

        Args:
            toolsets: Sequence of pydantic-ai tool objects, an AgentToolset
                (e.g., agent._function_toolset), or None.

        Note:
            Calling this method multiple times will overwrite the previous toolsets.
            A warning is logged when overwriting existing toolsets.
        """
        if MCP_SERVER_NAME in self._mcp_servers:
            logger.warning(
                "Overwriting existing MCP server '%s'. "
                "Previous toolsets will be replaced.",
                MCP_SERVER_NAME,
            )
        self._agent_toolsets = toolsets

        # Build tools cache for efficient lookup in _find_tools_by_names
        self._tools_cache = {}
        tools_for_mcp: Sequence[PydanticAITool] | None
        if isinstance(toolsets, AgentToolset):
            for name, tool in toolsets.tools.items():
                self._tools_cache[name] = tool
            tools_for_mcp = list(toolsets.tools.values())
        elif toolsets is not None:
            for tool in toolsets:
                self._tools_cache[tool.name] = tool
            tools_for_mcp = toolsets
        else:
            tools_for_mcp = None

        self._mcp_servers[MCP_SERVER_NAME] = create_mcp_server_from_tools(
            name=MCP_SERVER_NAME,
            toolsets=tools_for_mcp,
        )

        registered_names = list(self._tools_cache.keys())
        logger.debug(
            "set_agent_toolsets: registered %d tools, tool_names=%s",
            len(registered_names),
            registered_names,
        )

    def _find_tools_by_names(
        self,
        tool_names: list[str],
    ) -> tuple[list[PydanticAITool], list[str]]:
        """Find tools by name from registered toolsets using cached lookup.

        Uses the tools cache built during set_agent_toolsets() for O(1) lookup
        per tool name.

        Args:
            tool_names: List of tool names to find.

        Returns:
            A tuple of (found_tools, missing_tools):
                - found_tools: List of PydanticAITool objects that match the given names.
                - missing_tools: List of tool names that were not found.
        """
        if self._agent_toolsets is None:
            return [], list(tool_names)

        found_tools: list[PydanticAITool] = []
        missing_tools: list[str] = []

        for name in tool_names:
            if name in self._tools_cache:
                found_tools.append(self._tools_cache[name])
            else:
                missing_tools.append(name)

        return found_tools, missing_tools

    def _get_available_tool_names(self) -> list[str]:
        """Get list of available tool names from registered toolsets.

        Returns:
            List of tool names available in the tools cache.
        """
        return list(self._tools_cache.keys())

    def get_mcp_servers(self) -> dict[str, McpSdkServerConfig]:
        """Return registered MCP servers.

        Returns:
            Dictionary mapping server names to McpSdkServerConfig objects.
        """
        return self._mcp_servers

    def __repr__(self) -> str:
        return f"ClaudeCodeModel(model_name={self._model_name!r})"
