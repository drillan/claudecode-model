"""Shared test fixtures and helpers for claudecode_model tests."""

from claude_agent_sdk import ResultMessage


def create_mock_result_message(
    result: str = "Response from Claude",
    is_error: bool = False,
    subtype: str = "success",
    duration_ms: int = 1000,
    duration_api_ms: int = 800,
    num_turns: int = 1,
    session_id: str = "test-session",
    total_cost_usd: float | None = None,
    usage: dict[str, int] | None = None,
    structured_output: dict[str, object] | None = None,
) -> ResultMessage:
    """Create a mock ResultMessage for testing."""
    return ResultMessage(
        subtype=subtype,
        duration_ms=duration_ms,
        duration_api_ms=duration_api_ms,
        is_error=is_error,
        num_turns=num_turns,
        session_id=session_id,
        result=result,
        total_cost_usd=total_cost_usd,
        usage=usage
        or {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        structured_output=structured_output,
    )
