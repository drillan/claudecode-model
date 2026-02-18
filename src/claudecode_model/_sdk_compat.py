"""Temporary workaround: skip unknown SDK message types with a warning.

The SDK's ``parse_message`` raises ``MessageParseError`` for unrecognized
message types (e.g., ``rate_limit_event``). Because the error occurs inside
the SDK's async generator, it terminates the generator and loses subsequent
messages including ``ResultMessage``.

This module patches ``parse_message`` so that **only** unknown-type errors
return ``None`` (skipped with a warning log). All other ``MessageParseError``
cases (missing fields, malformed data) are re-raised as-is.

**Policy note**: This is NOT a fallback — it is an explicit, logged skip of
informational messages that are irrelevant to query results. The CLAUDE.md
"no fallback" policy targets silent error suppression and default-value
substitution; this module logs every skipped message and preserves all error
propagation for structurally invalid data.

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

# Matches the exact prefix from ``message_parser.py:180``:
#     ``raise MessageParseError(f"Unknown message type: {message_type}", data)``
# If the SDK changes this wording, the prefix match will fail and the
# exception will be re-raised — i.e. the code fails safe, not silent.
_UNKNOWN_TYPE_PREFIX = "Unknown message type: "


def _safe_parse_message(data: dict[str, object]) -> Message | None:
    """Wrapper around SDK's parse_message that returns None for unknown types.

    For unknown message types, logs a warning and returns None.
    For all other MessageParseError cases (missing fields, invalid data),
    re-raises the exception to preserve existing error handling.

    Note:
        The SDK's ``parse_message`` accepts ``dict[str, Any]`` but this
        wrapper uses ``dict[str, object]`` to comply with the project's
        ``Any`` type prohibition. The wider type is compatible at runtime.

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
                "Skipping unrecognized SDK message type: type=%s, data=%r",
                data.get("type") if isinstance(data, dict) else type(data).__name__,
                data,
            )
            return None
        raise


@contextmanager
def safe_message_parsing() -> Iterator[None]:
    """Context manager that patches parse_message to skip unknown message types.

    Patches the ``parse_message`` reference in the SDK's client module so that
    unknown message types return ``None`` instead of raising MessageParseError.
    The caller must filter ``None`` values from the message stream.

    Note:
        The patch is applied via ``unittest.mock.patch`` as a temporary
        workaround. This is acceptable because the entire module is
        intended to be removed when the upstream SDK is fixed.

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
