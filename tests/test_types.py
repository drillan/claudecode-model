"""Tests for claudecode_model.types module."""

import pytest
from pydantic import ValidationError

from claudecode_model.types import (
    CacheCreation,
    CLIResponse,
    CLIResponseData,
    CLIUsage,
    ClaudeCodeModelSettings,
    ModelUsageData,
    ServerToolUse,
    parse_cli_response,
)


class TestServerToolUse:
    """Tests for ServerToolUse model."""

    def test_default_values(self) -> None:
        """ServerToolUse should have default values of 0."""
        server_tool_use = ServerToolUse()
        assert server_tool_use.web_search_requests == 0
        assert server_tool_use.web_fetch_requests == 0

    def test_valid_values(self) -> None:
        """ServerToolUse should accept valid values."""
        server_tool_use = ServerToolUse(web_search_requests=5, web_fetch_requests=3)
        assert server_tool_use.web_search_requests == 5
        assert server_tool_use.web_fetch_requests == 3

    def test_rejects_negative_web_search_requests(self) -> None:
        """ServerToolUse should reject negative web_search_requests."""
        with pytest.raises(ValidationError):
            ServerToolUse(web_search_requests=-1, web_fetch_requests=0)

    def test_rejects_negative_web_fetch_requests(self) -> None:
        """ServerToolUse should reject negative web_fetch_requests."""
        with pytest.raises(ValidationError):
            ServerToolUse(web_search_requests=0, web_fetch_requests=-1)


class TestCacheCreation:
    """Tests for CacheCreation model."""

    def test_default_values(self) -> None:
        """CacheCreation should have default values of 0."""
        cache_creation = CacheCreation()
        assert cache_creation.ephemeral_1h_input_tokens == 0
        assert cache_creation.ephemeral_5m_input_tokens == 0

    def test_valid_values(self) -> None:
        """CacheCreation should accept valid values."""
        cache_creation = CacheCreation(
            ephemeral_1h_input_tokens=100, ephemeral_5m_input_tokens=200
        )
        assert cache_creation.ephemeral_1h_input_tokens == 100
        assert cache_creation.ephemeral_5m_input_tokens == 200

    def test_rejects_negative_ephemeral_1h_input_tokens(self) -> None:
        """CacheCreation should reject negative ephemeral_1h_input_tokens."""
        with pytest.raises(ValidationError):
            CacheCreation(ephemeral_1h_input_tokens=-1, ephemeral_5m_input_tokens=0)

    def test_rejects_negative_ephemeral_5m_input_tokens(self) -> None:
        """CacheCreation should reject negative ephemeral_5m_input_tokens."""
        with pytest.raises(ValidationError):
            CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=-1)


class TestModelUsageData:
    """Tests for ModelUsageData model."""

    def test_requires_all_fields(self) -> None:
        """ModelUsageData should require all fields."""
        with pytest.raises(ValidationError):
            ModelUsageData()  # type: ignore[call-arg]

    def test_valid_values_with_alias(self) -> None:
        """ModelUsageData should accept values using camelCase aliases (JSON format)."""
        model_usage = ModelUsageData(
            inputTokens=100,
            outputTokens=50,
            cacheReadInputTokens=200,
            cacheCreationInputTokens=300,
            webSearchRequests=1,
            costUSD=0.05,
            contextWindow=200000,
            maxOutputTokens=64000,
        )
        assert model_usage.input_tokens == 100
        assert model_usage.output_tokens == 50
        assert model_usage.cache_read_input_tokens == 200
        assert model_usage.cache_creation_input_tokens == 300
        assert model_usage.web_search_requests == 1
        assert model_usage.cost_usd == 0.05
        assert model_usage.context_window == 200000
        assert model_usage.max_output_tokens == 64000

    def test_valid_values_with_snake_case(self) -> None:
        """ModelUsageData should accept values using snake_case via model_validate."""
        model_usage = ModelUsageData.model_validate(
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 300,
                "web_search_requests": 1,
                "cost_usd": 0.05,
                "context_window": 200000,
                "max_output_tokens": 64000,
            }
        )
        assert model_usage.input_tokens == 100
        assert model_usage.output_tokens == 50
        assert model_usage.cache_read_input_tokens == 200
        assert model_usage.cache_creation_input_tokens == 300
        assert model_usage.web_search_requests == 1
        assert model_usage.cost_usd == 0.05
        assert model_usage.context_window == 200000
        assert model_usage.max_output_tokens == 64000

    def test_rejects_negative_input_tokens(self) -> None:
        """ModelUsageData should reject negative input_tokens."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=-1,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_output_tokens(self) -> None:
        """ModelUsageData should reject negative output_tokens."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=-1,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_cost_usd(self) -> None:
        """ModelUsageData should reject negative cost_usd."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=-0.01,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_cache_read_input_tokens(self) -> None:
        """ModelUsageData should reject negative cache_read_input_tokens."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=-1,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_cache_creation_input_tokens(self) -> None:
        """ModelUsageData should reject negative cache_creation_input_tokens."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=-1,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_web_search_requests(self) -> None:
        """ModelUsageData should reject negative web_search_requests."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=-1,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
            )

    def test_rejects_negative_context_window(self) -> None:
        """ModelUsageData should reject negative context_window."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=-1,
                maxOutputTokens=0,
            )

    def test_rejects_negative_max_output_tokens(self) -> None:
        """ModelUsageData should reject negative max_output_tokens."""
        with pytest.raises(ValidationError):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=-1,
            )

    def test_model_dump_uses_alias_by_default(self) -> None:
        """ModelUsageData.model_dump should use camelCase aliases by default."""
        model_usage = ModelUsageData(
            inputTokens=100,
            outputTokens=50,
            cacheReadInputTokens=200,
            cacheCreationInputTokens=300,
            webSearchRequests=1,
            costUSD=0.05,
            contextWindow=200000,
            maxOutputTokens=64000,
        )
        dumped = model_usage.model_dump(by_alias=True)
        assert "inputTokens" in dumped
        assert "outputTokens" in dumped
        assert "cacheReadInputTokens" in dumped
        assert "cacheCreationInputTokens" in dumped
        assert "webSearchRequests" in dumped
        assert "costUSD" in dumped
        assert "contextWindow" in dumped
        assert "maxOutputTokens" in dumped
        assert dumped["inputTokens"] == 100
        assert dumped["costUSD"] == 0.05

    def test_model_dump_uses_field_names(self) -> None:
        """ModelUsageData.model_dump should use snake_case field names."""
        model_usage = ModelUsageData(
            inputTokens=100,
            outputTokens=50,
            cacheReadInputTokens=200,
            cacheCreationInputTokens=300,
            webSearchRequests=1,
            costUSD=0.05,
            contextWindow=200000,
            maxOutputTokens=64000,
        )
        dumped = model_usage.model_dump()
        assert "input_tokens" in dumped
        assert "output_tokens" in dumped
        assert "cache_read_input_tokens" in dumped
        assert "cache_creation_input_tokens" in dumped
        assert "web_search_requests" in dumped
        assert "cost_usd" in dumped
        assert "context_window" in dumped
        assert "max_output_tokens" in dumped
        assert dumped["input_tokens"] == 100
        assert dumped["cost_usd"] == 0.05

    def test_rejects_extra_fields(self) -> None:
        """ModelUsageData should reject extra fields (extra='forbid')."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            ModelUsageData(
                inputTokens=0,
                outputTokens=0,
                cacheReadInputTokens=0,
                cacheCreationInputTokens=0,
                webSearchRequests=0,
                costUSD=0.0,
                contextWindow=0,
                maxOutputTokens=0,
                unknownField=123,  # type: ignore[call-arg]
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

    def test_new_optional_fields_with_defaults(self) -> None:
        """CLIUsage should have new optional fields with defaults."""
        usage = CLIUsage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=5,
        )
        assert usage.server_tool_use is None
        assert usage.service_tier is None
        assert usage.cache_creation is None

    def test_new_optional_fields_with_values(self) -> None:
        """CLIUsage should accept new optional fields."""
        usage = CLIUsage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=5,
            server_tool_use=ServerToolUse(web_search_requests=1, web_fetch_requests=2),
            service_tier="standard",
            cache_creation=CacheCreation(
                ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=7365
            ),
        )
        assert usage.server_tool_use is not None
        assert usage.server_tool_use.web_search_requests == 1
        assert usage.server_tool_use.web_fetch_requests == 2
        assert usage.service_tier == "standard"
        assert usage.cache_creation is not None
        assert usage.cache_creation.ephemeral_5m_input_tokens == 7365


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
        assert response.model_usage is None
        assert response.permission_denials is None
        assert response.uuid is None

    def test_new_optional_fields_with_values(self) -> None:
        """CLIResponse should accept new optional fields."""
        model_usage_data = ModelUsageData(
            inputTokens=2,
            outputTokens=13,
            cacheReadInputTokens=16464,
            cacheCreationInputTokens=7365,
            webSearchRequests=0,
            costUSD=0.05459825,
            contextWindow=200000,
            maxOutputTokens=64000,
        )
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=2778,
            duration_api_ms=2751,
            num_turns=1,
            result="1 + 1 = 2",
            session_id="7d696607-e82d-494f-a633-f55acb3f3c44",
            total_cost_usd=0.05459825,
            usage=CLIUsage(
                input_tokens=2,
                output_tokens=13,
                cache_creation_input_tokens=7365,
                cache_read_input_tokens=16464,
            ),
            modelUsage={"claude-opus-4-5-20251101": model_usage_data},
            permission_denials=[],
            uuid="0364bc35-e562-4b82-8b8b-f6c80677d13a",
        )
        assert response.model_usage is not None
        assert "claude-opus-4-5-20251101" in response.model_usage
        assert response.model_usage["claude-opus-4-5-20251101"].input_tokens == 2
        assert response.permission_denials == []
        assert response.uuid == "0364bc35-e562-4b82-8b8b-f6c80677d13a"

    def test_permission_denials_with_values(self) -> None:
        """CLIResponse should accept non-empty permission_denials list."""
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
            permission_denials=[
                "User denied permission to run: rm -rf /",
                "User denied permission to run: sudo apt install",
            ],
        )
        assert response.permission_denials is not None
        assert len(response.permission_denials) == 2
        assert "rm -rf /" in response.permission_denials[0]
        assert "sudo apt install" in response.permission_denials[1]

    def test_multiple_models_in_model_usage(self) -> None:
        """CLIResponse should accept model_usage with multiple models."""
        model_usage_opus = ModelUsageData(
            inputTokens=100,
            outputTokens=50,
            cacheReadInputTokens=0,
            cacheCreationInputTokens=0,
            webSearchRequests=0,
            costUSD=0.05,
            contextWindow=200000,
            maxOutputTokens=64000,
        )
        model_usage_haiku = ModelUsageData(
            inputTokens=200,
            outputTokens=100,
            cacheReadInputTokens=0,
            cacheCreationInputTokens=0,
            webSearchRequests=0,
            costUSD=0.01,
            contextWindow=200000,
            maxOutputTokens=8192,
        )
        response = CLIResponse(
            type="result",
            subtype="success",
            is_error=False,
            duration_ms=3000,
            duration_api_ms=2500,
            num_turns=2,
            result="test result",
            usage=CLIUsage(
                input_tokens=300,
                output_tokens=150,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            modelUsage={
                "claude-opus-4-5-20251101": model_usage_opus,
                "claude-3-5-haiku-20241022": model_usage_haiku,
            },
        )
        assert response.model_usage is not None
        assert len(response.model_usage) == 2
        assert "claude-opus-4-5-20251101" in response.model_usage
        assert "claude-3-5-haiku-20241022" in response.model_usage
        assert response.model_usage["claude-opus-4-5-20251101"].input_tokens == 100
        assert response.model_usage["claude-3-5-haiku-20241022"].input_tokens == 200
        assert response.model_usage["claude-3-5-haiku-20241022"].cost_usd == 0.01

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

    def test_parses_full_cli_response_with_new_fields(self) -> None:
        """parse_cli_response should parse full CLI response with new fields."""
        data: CLIResponseData = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 2778,
            "duration_api_ms": 2751,
            "num_turns": 1,
            "result": "1 + 1 = 2",
            "session_id": "7d696607-e82d-494f-a633-f55acb3f3c44",
            "total_cost_usd": 0.05459825,
            "usage": {
                "input_tokens": 2,
                "output_tokens": 13,
                "cache_creation_input_tokens": 7365,
                "cache_read_input_tokens": 16464,
                "server_tool_use": {
                    "web_search_requests": 0,
                    "web_fetch_requests": 0,
                },
                "service_tier": "standard",
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 0,
                    "ephemeral_5m_input_tokens": 7365,
                },
            },
            "model_usage": {
                "claude-opus-4-5-20251101": {
                    "inputTokens": 2,
                    "outputTokens": 13,
                    "cacheReadInputTokens": 16464,
                    "cacheCreationInputTokens": 7365,
                    "webSearchRequests": 0,
                    "costUSD": 0.05459825,
                    "contextWindow": 200000,
                    "maxOutputTokens": 64000,
                }
            },
            "permission_denials": [],
            "uuid": "0364bc35-e562-4b82-8b8b-f6c80677d13a",
        }

        response = parse_cli_response(data)

        assert response.type == "result"
        assert response.result == "1 + 1 = 2"
        assert response.usage.input_tokens == 2
        assert response.usage.server_tool_use is not None
        assert response.usage.server_tool_use.web_search_requests == 0
        assert response.usage.service_tier == "standard"
        assert response.usage.cache_creation is not None
        assert response.usage.cache_creation.ephemeral_5m_input_tokens == 7365
        assert response.model_usage is not None
        assert "claude-opus-4-5-20251101" in response.model_usage
        assert response.model_usage["claude-opus-4-5-20251101"].input_tokens == 2
        assert response.permission_denials == []
        assert response.uuid == "0364bc35-e562-4b82-8b8b-f6c80677d13a"


class TestClaudeCodeModelSettings:
    """Tests for ClaudeCodeModelSettings TypedDict."""

    def test_accepts_timeout(self) -> None:
        """ClaudeCodeModelSettings should accept timeout."""
        settings: ClaudeCodeModelSettings = {"timeout": 60.0}
        assert settings["timeout"] == 60.0

    def test_accepts_max_budget_usd(self) -> None:
        """ClaudeCodeModelSettings should accept max_budget_usd."""
        settings: ClaudeCodeModelSettings = {"max_budget_usd": 1.0}
        assert settings["max_budget_usd"] == 1.0

    def test_accepts_append_system_prompt(self) -> None:
        """ClaudeCodeModelSettings should accept append_system_prompt."""
        settings: ClaudeCodeModelSettings = {"append_system_prompt": "Be concise"}
        assert settings["append_system_prompt"] == "Be concise"

    def test_accepts_all_options(self) -> None:
        """ClaudeCodeModelSettings should accept all options together."""
        settings: ClaudeCodeModelSettings = {
            "timeout": 120.0,
            "max_budget_usd": 0.5,
            "append_system_prompt": "You are a helpful assistant.",
            "max_turns": 5,
        }
        assert settings["timeout"] == 120.0
        assert settings["max_budget_usd"] == 0.5
        assert settings["append_system_prompt"] == "You are a helpful assistant."
        assert settings["max_turns"] == 5

    def test_accepts_max_turns(self) -> None:
        """ClaudeCodeModelSettings should accept max_turns."""
        settings: ClaudeCodeModelSettings = {"max_turns": 10}
        assert settings["max_turns"] == 10
