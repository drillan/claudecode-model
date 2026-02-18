"""Temporary compatibility layer for claude_agent_sdk message parsing.

Patches the SDK's parse_message function to gracefully handle unknown message
types (e.g., rate_limit_event) that the SDK does not yet recognize. Without
this patch, unknown message types cause MessageParseError inside the SDK's
async generator, terminating it and losing subsequent messages like ResultMessage.

Remove this module when upstream SDK handles unknown message types:
    https://github.com/anthropics/claude-agent-sdk-python/issues/583
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from collections.abc import Iterator

from unittest.mock import patch

from claude_agent_sdk._errors import MessageParseError
from claude_agent_sdk._internal.message_parser import (
    parse_message as _original_parse_message,
)
from claude_agent_sdk.types import Message

logger = logging.getLogger(__name__)

_UNKNOWN_TYPE_PREFIX = "Unknown message type: "


def _safe_parse_message(data: dict[str, object]) -> Message | None:
    """Wrapper around SDK's parse_message that returns None for unknown types.

    For unknown message types, logs a warning and returns None.
    For all other MessageParseError cases (missing fields, invalid data),
    re-raises the exception to preserve existing error handling.

    Args:
        data: Raw message dictionary from CLI output.

    Returns:
        Parsed Message object, or None if the message type is unknown.

    Raises:
        MessageParseError: If parsing fails for reasons other than unknown type.
    """
    try:
        return _original_parse_message(data)
    except MessageParseError as e:
        if str(e).startswith(_UNKNOWN_TYPE_PREFIX):
            logger.warning(
                "Skipping unrecognized SDK message type: %s (data keys: %s)",
                e,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return None
        raise


@contextmanager
def safe_message_parsing() -> Iterator[None]:
    """Context manager that patches parse_message to skip unknown message types.

    Patches ``claude_agent_sdk._internal.client.parse_message`` (the import
    reference used in the ``yield`` statement of ``process_query``) so that
    unknown message types return ``None`` instead of raising MessageParseError.

    Usage::

        with safe_message_parsing():
            query_generator = query(prompt=prompt, options=options)
            async for message in query_generator:
                if message is None:
                    continue
                process(message)
    """
    with patch(
        "claude_agent_sdk._internal.client.parse_message",
        _safe_parse_message,
    ):
        yield
