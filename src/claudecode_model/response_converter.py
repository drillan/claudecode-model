"""Converter functions for Claude Agent SDK messages to CLIResponse format."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from claude_agent_sdk.types import (
    AssistantMessage,
    Message,
    ResultMessage,
    TextBlock,
)

from claudecode_model.types import (
    CacheCreation,
    CLIResponse,
    CLIUsage,
    JsonValue,
    ServerToolUse,
)

logger = logging.getLogger(__name__)


def _safe_int(value: JsonValue, default: int = 0, *, field_name: str = "") -> int:
    """Safely convert JsonValue to int with warning on unexpected types.

    Args:
        value: The value to convert.
        default: Default value if conversion fails.
        field_name: Name of the field being converted (for logging).

    Returns:
        Integer value or default.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        # bool is subclass of int, but we want to treat True/False as 1/0
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            logger.warning(
                "Failed to convert string to int for field '%s': %r, using default %d",
                field_name,
                value,
                default,
            )
            return default
    # Unexpected type (list, dict, etc.)
    logger.warning(
        "Unexpected type for field '%s': %s (value: %r), using default %d",
        field_name,
        type(value).__name__,
        value,
        default,
    )
    return default


def extract_text_from_assistant_message(message: AssistantMessage) -> str:
    """Extract text content from AssistantMessage.

    Extracts only text from TextBlock elements, ignoring ThinkingBlock
    and ToolUseBlock.

    Args:
        message: The AssistantMessage to extract text from.

    Returns:
        Extracted text joined with newlines. Returns empty string if no TextBlocks.
    """
    texts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)
    return "\n".join(texts)


def convert_usage_dict_to_cli_usage(
    usage: dict[str, JsonValue] | None,
) -> CLIUsage:
    """Convert SDK usage dict to CLIUsage model.

    Args:
        usage: The usage dict from SDK ResultMessage, or None.

    Returns:
        CLIUsage instance with converted values. Returns default CLIUsage
        (all zeros) if usage is None.
    """
    if usage is None:
        return CLIUsage(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )

    # Extract basic token counts with defaults using _safe_int
    input_tokens = _safe_int(usage.get("input_tokens"), field_name="input_tokens")
    output_tokens = _safe_int(usage.get("output_tokens"), field_name="output_tokens")
    cache_creation_input_tokens = _safe_int(
        usage.get("cache_creation_input_tokens"),
        field_name="cache_creation_input_tokens",
    )
    cache_read_input_tokens = _safe_int(
        usage.get("cache_read_input_tokens"), field_name="cache_read_input_tokens"
    )
    service_tier = usage.get("service_tier")

    # Convert server_tool_use if present
    server_tool_use: ServerToolUse | None = None
    server_tool_use_data = usage.get("server_tool_use")
    if isinstance(server_tool_use_data, dict):
        server_tool_use = ServerToolUse(
            web_search_requests=_safe_int(
                server_tool_use_data.get("web_search_requests"),
                field_name="server_tool_use.web_search_requests",
            ),
            web_fetch_requests=_safe_int(
                server_tool_use_data.get("web_fetch_requests"),
                field_name="server_tool_use.web_fetch_requests",
            ),
        )

    # Convert cache_creation if present
    cache_creation: CacheCreation | None = None
    cache_creation_data = usage.get("cache_creation")
    if isinstance(cache_creation_data, dict):
        cache_creation = CacheCreation(
            ephemeral_1h_input_tokens=_safe_int(
                cache_creation_data.get("ephemeral_1h_input_tokens"),
                field_name="cache_creation.ephemeral_1h_input_tokens",
            ),
            ephemeral_5m_input_tokens=_safe_int(
                cache_creation_data.get("ephemeral_5m_input_tokens"),
                field_name="cache_creation.ephemeral_5m_input_tokens",
            ),
        )

    return CLIUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        service_tier=str(service_tier) if service_tier is not None else None,
        server_tool_use=server_tool_use,
        cache_creation=cache_creation,
    )


def convert_sdk_messages_to_cli_response(
    messages: Sequence[Message],
    *,
    default_type: str = "result",
) -> CLIResponse:
    """Convert Claude Agent SDK messages to CLIResponse format.

    If multiple ResultMessage objects are present in the messages list,
    the last one is used for extracting response metadata.

    Args:
        messages: List of SDK Message objects. Must contain at least one ResultMessage.
        default_type: Default value for the 'type' field. Defaults to "result".

    Returns:
        CLIResponse instance with converted data.

    Raises:
        ValueError: If messages list is empty or contains no ResultMessage.
    """
    if not messages:
        raise ValueError("messages list cannot be empty")

    # Find ResultMessage (use the last one if multiple)
    result_message: ResultMessage | None = None
    for msg in messages:
        if isinstance(msg, ResultMessage):
            result_message = msg

    if result_message is None:
        raise ValueError("ResultMessage is required in messages list")

    # Extract text from all AssistantMessages
    assistant_texts: list[str] = []
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            text = extract_text_from_assistant_message(msg)
            if text:
                assistant_texts.append(text)

    # Determine result text: ResultMessage.result takes priority
    result_text = result_message.result
    if result_text is None:
        result_text = "\n".join(assistant_texts) if assistant_texts else ""

    # Handle structured_output (only dict type is valid)
    structured_output: dict[str, JsonValue] | None = None
    if isinstance(result_message.structured_output, dict):
        structured_output = result_message.structured_output

    # Convert usage
    usage = convert_usage_dict_to_cli_usage(result_message.usage)

    # Note: Fields not available from SDK (model_usage, permission_denials, uuid, errors)
    # will use their default values of None from CLIResponse
    return CLIResponse(
        type=default_type,
        subtype=result_message.subtype,
        is_error=result_message.is_error,
        duration_ms=result_message.duration_ms,
        duration_api_ms=result_message.duration_api_ms,
        num_turns=result_message.num_turns,
        result=result_text,
        session_id=result_message.session_id,
        total_cost_usd=result_message.total_cost_usd,
        usage=usage,
        structured_output=structured_output,
    )
