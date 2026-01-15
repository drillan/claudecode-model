"""Tests for claudecode_model.types module."""

import pytest
from pydantic import ValidationError

from claudecode_model.types import (
    CLIResponse,
    CLIResponseData,
    CLIUsage,
    parse_cli_response,
)


class TestCLIUsage:
    """Tests for CLIUsage model."""

    def test_requires_all_fields(self) -> None:
        """CLIUsage should require all token fields."""
        with pytest.raises(ValidationError):
            CLIUsage()  # type: ignore[call-arg]

    def test_valid_usage(self) -> None:
        """CLIUsage should accept valid token counts."""
        usage = CLIUsage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=5,
        )
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_creation_input_tokens == 10
        assert usage.cache_read_input_tokens == 5


class TestCLIResponse:
    """Tests for CLIResponse model."""

    def test_requires_mandatory_fields(self) -> None:
        """CLIResponse should require all mandatory fields."""
        with pytest.raises(ValidationError):
            CLIResponse()  # type: ignore[call-arg]

    def test_valid_response(self) -> None:
        """CLIResponse should accept valid data."""
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            result="Hello, world!",
            usage=CLIUsage(
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )
        assert response.type == "result"
        assert response.subtype == "success"
        assert response.is_error is False
        assert response.result == "Hello, world!"

    def test_optional_fields_default_to_none(self) -> None:
        """Optional fields should default to None."""
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            result="test",
            usage=CLIUsage(
                input_tokens=0,
                output_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )
        assert response.session_id is None
        assert response.total_cost_usd is None

    def test_rejects_extra_fields(self) -> None:
        """CLIResponse should reject extra fields (extra='forbid')."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            CLIResponse(
                type="result",
                subtype="success",
                is_error=False,
                duration_ms=1000,
                duration_api_ms=800,
                num_turns=1,
                result="test",
                usage=CLIUsage(
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                unknown_field="should fail",  # type: ignore[call-arg]
            )

    def test_to_model_response(self) -> None:
        """to_model_response should convert to pydantic-ai ModelResponse."""
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            result="Hello!",
            usage=CLIUsage(
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=10,
                cache_read_input_tokens=5,
            ),
        )

        model_response = response.to_model_response(model_name="test-model")

        assert len(model_response.parts) == 1
        assert model_response.parts[0].content == "Hello!"  # type: ignore[union-attr]
        assert model_response.model_name == "test-model"
        assert model_response.usage is not None
        assert model_response.usage.input_tokens == 100
        assert model_response.usage.output_tokens == 50

    def test_to_model_response_without_model_name(self) -> None:
        """to_model_response should work without model_name."""
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=0,
            duration_api_ms=0,
            num_turns=1,
            result="test",
            usage=CLIUsage(
                input_tokens=0,
                output_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )

        model_response = response.to_model_response()
        assert model_response.model_name is None


class TestParseCLIResponse:
    """Tests for parse_cli_response function."""

    def test_parses_valid_json_data(self) -> None:
        """parse_cli_response should parse valid JSON data."""
        data: CLIResponseData = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 500,
            "duration_api_ms": 400,
            "num_turns": 1,
            "result": "parsed result",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }

        response = parse_cli_response(data)

        assert response.type == "result"
        assert response.result == "parsed result"
        assert response.usage.input_tokens == 10

    def test_raises_on_missing_required_fields(self) -> None:
        """parse_cli_response should raise ValidationError on missing fields."""
        incomplete_data: CLIResponseData = {
            "type": "result",
            # Missing other required fields
        }

        with pytest.raises(ValidationError):
            parse_cli_response(incomplete_data)

    def test_raises_on_invalid_types(self) -> None:
        """parse_cli_response should raise ValidationError on invalid types."""
        invalid_data: CLIResponseData = {
            "type": "result",
            "subtype": "success",
            "is_error": "not a bool",  # type: ignore[typeddict-item]
            "duration_ms": 0,
            "duration_api_ms": 0,
            "num_turns": 1,
            "result": "test",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }

        with pytest.raises(ValidationError):
            parse_cli_response(invalid_data)
