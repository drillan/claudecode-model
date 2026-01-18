"""Tests for deps_support module - serializable dependency support."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel


class UserConfig(BaseModel):
    """Test Pydantic model for dependencies."""

    username: str
    api_key: str
    timeout: int = 30


@dataclass
class AppSettings:
    """Test dataclass for dependencies."""

    debug: bool
    max_retries: int
    base_url: str


@dataclass
class NestedSettings:
    """Test dataclass with nested dataclass."""

    name: str
    inner: AppSettings


class TestIsSerializableType:
    """Tests for is_serializable_type function."""

    def test_primitive_types_are_serializable(self) -> None:
        """Primitive types (str, int, float, bool, None) should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(str) is True
        assert is_serializable_type(int) is True
        assert is_serializable_type(float) is True
        assert is_serializable_type(bool) is True
        assert is_serializable_type(type(None)) is True

    def test_dict_is_serializable(self) -> None:
        """dict type should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(dict) is True

    def test_list_is_serializable(self) -> None:
        """list type should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(list) is True

    def test_dataclass_is_serializable(self) -> None:
        """dataclass types should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(AppSettings) is True

    def test_nested_dataclass_is_serializable(self) -> None:
        """Nested dataclass types should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(NestedSettings) is True

    def test_pydantic_model_is_serializable(self) -> None:
        """Pydantic BaseModel types should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(UserConfig) is True

    def test_httpx_client_is_not_serializable(self) -> None:
        """httpx.AsyncClient should not be serializable."""
        import httpx

        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(httpx.AsyncClient) is False

    def test_arbitrary_class_is_not_serializable(self) -> None:
        """Arbitrary classes without serialization support should not be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        class SomeClass:
            pass

        assert is_serializable_type(SomeClass) is False


class TestGenericTypeSerializability:
    """Tests for generic type serializability checking."""

    def test_list_with_str_is_serializable(self) -> None:
        """list[str] should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(list[str]) is True

    def test_list_with_int_is_serializable(self) -> None:
        """list[int] should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(list[int]) is True

    def test_dict_with_str_int_is_serializable(self) -> None:
        """dict[str, int] should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(dict[str, int]) is True

    def test_optional_str_is_serializable(self) -> None:
        """Optional[str] (str | None) should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(str | None) is True

    def test_list_with_non_serializable_is_not_serializable(self) -> None:
        """list[SomeClass] where SomeClass is not serializable should fail."""
        import httpx

        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(list[httpx.AsyncClient]) is False

    def test_nested_generic_is_serializable(self) -> None:
        """list[dict[str, int]] should be serializable."""
        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(list[dict[str, int]]) is True

    def test_union_with_non_serializable_is_not_serializable(self) -> None:
        """Union with non-serializable type should fail."""
        import httpx

        from claudecode_model.deps_support import is_serializable_type

        assert is_serializable_type(str | httpx.AsyncClient) is False


class TestSerializeDeps:
    """Tests for serialize_deps function."""

    def test_serializes_dict(self) -> None:
        """dict should serialize to JSON."""
        from claudecode_model.deps_support import serialize_deps

        deps = {"key": "value", "count": 42}
        result = serialize_deps(deps)

        assert json.loads(result) == deps

    def test_serializes_list(self) -> None:
        """list should serialize to JSON."""
        from claudecode_model.deps_support import serialize_deps

        deps = [1, 2, "three"]
        result = serialize_deps(deps)

        assert json.loads(result) == deps

    def test_serializes_primitives(self) -> None:
        """Primitive values should serialize to JSON."""
        from claudecode_model.deps_support import serialize_deps

        assert json.loads(serialize_deps("hello")) == "hello"
        assert json.loads(serialize_deps(42)) == 42
        assert json.loads(serialize_deps(3.14)) == 3.14
        assert json.loads(serialize_deps(True)) is True
        assert json.loads(serialize_deps(None)) is None

    def test_serializes_dataclass(self) -> None:
        """dataclass should serialize via asdict to JSON."""
        from claudecode_model.deps_support import serialize_deps

        deps = AppSettings(
            debug=True, max_retries=3, base_url="https://api.example.com"
        )
        result = serialize_deps(deps)

        parsed = json.loads(result)
        assert parsed == {
            "debug": True,
            "max_retries": 3,
            "base_url": "https://api.example.com",
        }

    def test_serializes_nested_dataclass(self) -> None:
        """Nested dataclass should serialize recursively."""
        from claudecode_model.deps_support import serialize_deps

        inner = AppSettings(debug=False, max_retries=5, base_url="http://localhost")
        deps = NestedSettings(name="test", inner=inner)
        result = serialize_deps(deps)

        parsed = json.loads(result)
        assert parsed == {
            "name": "test",
            "inner": {
                "debug": False,
                "max_retries": 5,
                "base_url": "http://localhost",
            },
        }

    def test_serializes_pydantic_model(self) -> None:
        """Pydantic BaseModel should serialize via model_dump_json."""
        from claudecode_model.deps_support import serialize_deps

        deps = UserConfig(username="alice", api_key="secret123", timeout=60)
        result = serialize_deps(deps)

        parsed = json.loads(result)
        assert parsed == {"username": "alice", "api_key": "secret123", "timeout": 60}

    def test_raises_on_unsupported_type(self) -> None:
        """Unsupported types should raise UnsupportedDepsTypeError."""
        import httpx

        from claudecode_model.deps_support import serialize_deps
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        client = httpx.AsyncClient()
        try:
            with pytest.raises(UnsupportedDepsTypeError) as exc_info:
                serialize_deps(client)

            assert "AsyncClient" in str(exc_info.value)
        finally:
            # Clean up using asyncio.run for Python 3.10+ compatibility
            import asyncio

            asyncio.run(client.aclose())


class TestDeserializeDeps:
    """Tests for deserialize_deps function."""

    def test_deserializes_to_dict(self) -> None:
        """JSON should deserialize to dict when no type hint provided."""
        from claudecode_model.deps_support import deserialize_deps

        json_str = '{"key": "value", "count": 42}'
        result = deserialize_deps(json_str, dict)

        assert result == {"key": "value", "count": 42}

    def test_deserializes_to_list(self) -> None:
        """JSON should deserialize to list when list type provided."""
        from claudecode_model.deps_support import deserialize_deps

        json_str = "[1, 2, 3]"
        result = deserialize_deps(json_str, list)

        assert result == [1, 2, 3]

    def test_deserializes_to_dataclass(self) -> None:
        """JSON should deserialize to dataclass when dataclass type provided."""
        from claudecode_model.deps_support import deserialize_deps

        json_str = (
            '{"debug": true, "max_retries": 3, "base_url": "https://api.example.com"}'
        )
        result = deserialize_deps(json_str, AppSettings)

        assert isinstance(result, AppSettings)
        assert result.debug is True
        assert result.max_retries == 3
        assert result.base_url == "https://api.example.com"

    def test_deserializes_to_pydantic_model(self) -> None:
        """JSON should deserialize to Pydantic model when model type provided."""
        from claudecode_model.deps_support import deserialize_deps

        json_str = '{"username": "alice", "api_key": "secret123", "timeout": 60}'
        result = deserialize_deps(json_str, UserConfig)

        assert isinstance(result, UserConfig)
        assert result.username == "alice"
        assert result.api_key == "secret123"
        assert result.timeout == 60

    def test_deserializes_primitives(self) -> None:
        """Primitive JSON values should deserialize correctly."""
        from claudecode_model.deps_support import deserialize_deps

        assert deserialize_deps('"hello"', str) == "hello"
        assert deserialize_deps("42", int) == 42
        assert deserialize_deps("3.14", float) == 3.14
        assert deserialize_deps("true", bool) is True
        assert deserialize_deps("null", type(None)) is None

    def test_deserializes_nested_dataclass(self) -> None:
        """Nested dataclass should deserialize recursively."""
        from claudecode_model.deps_support import deserialize_deps

        json_str = json.dumps(
            {
                "name": "test",
                "inner": {
                    "debug": False,
                    "max_retries": 5,
                    "base_url": "http://localhost",
                },
            }
        )
        result = deserialize_deps(json_str, NestedSettings)

        assert isinstance(result, NestedSettings)
        assert result.name == "test"
        assert isinstance(result.inner, AppSettings)
        assert result.inner.debug is False
        assert result.inner.max_retries == 5
        assert result.inner.base_url == "http://localhost"

    def test_raises_on_invalid_json(self) -> None:
        """Invalid JSON should raise json.JSONDecodeError."""
        from claudecode_model.deps_support import deserialize_deps

        with pytest.raises(json.JSONDecodeError):
            deserialize_deps("not valid json", dict)


class TestUnsupportedDepsTypeError:
    """Tests for UnsupportedDepsTypeError exception."""

    def test_error_message_contains_type_name(self) -> None:
        """Error message should include the unsupported type name."""
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        error = UnsupportedDepsTypeError("httpx.AsyncClient")

        assert "httpx.AsyncClient" in str(error)

    def test_is_claude_code_error_subclass(self) -> None:
        """UnsupportedDepsTypeError should be a subclass of ClaudeCodeError."""
        from claudecode_model.exceptions import (
            ClaudeCodeError,
            UnsupportedDepsTypeError,
        )

        assert issubclass(UnsupportedDepsTypeError, ClaudeCodeError)

    def test_error_has_type_name_attribute(self) -> None:
        """Error should have type_name attribute for programmatic access."""
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        error = UnsupportedDepsTypeError("SomeClass")

        assert error.type_name == "SomeClass"


class TestCreateSerializableDepsContext:
    """Tests for creating serializable deps context."""

    def test_creates_context_with_dict_deps(self) -> None:
        """Should create context that provides serialized dict deps."""
        from claudecode_model.deps_support import create_deps_context

        deps = {"api_url": "https://example.com", "retries": 3}
        context = create_deps_context(deps)

        assert context.deps == deps

    def test_creates_context_with_dataclass_deps(self) -> None:
        """Should create context that provides dataclass deps."""
        from claudecode_model.deps_support import create_deps_context

        deps = AppSettings(debug=True, max_retries=5, base_url="http://localhost")
        context = create_deps_context(deps)

        assert context.deps == deps

    def test_creates_context_with_pydantic_model_deps(self) -> None:
        """Should create context that provides Pydantic model deps."""
        from claudecode_model.deps_support import create_deps_context

        deps = UserConfig(username="bob", api_key="key456")
        context = create_deps_context(deps)

        assert context.deps == deps

    def test_create_deps_context_raises_on_non_serializable(self) -> None:
        """create_deps_context should raise UnsupportedDepsTypeError for non-serializable deps."""
        import asyncio

        import httpx

        from claudecode_model.deps_support import create_deps_context
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        client = httpx.AsyncClient()
        try:
            with pytest.raises(UnsupportedDepsTypeError) as exc_info:
                create_deps_context(client)

            assert "AsyncClient" in str(exc_info.value)
        finally:
            asyncio.run(client.aclose())


class TestDepsContextConstructorValidation:
    """Tests for DepsContext constructor validation."""

    def test_deps_context_constructor_raises_on_non_serializable(self) -> None:
        """DepsContext constructor should raise UnsupportedDepsTypeError for non-serializable deps."""
        import asyncio

        import httpx

        from claudecode_model.deps_support import DepsContext
        from claudecode_model.exceptions import UnsupportedDepsTypeError

        client = httpx.AsyncClient()
        try:
            with pytest.raises(UnsupportedDepsTypeError) as exc_info:
                DepsContext(client)

            assert "AsyncClient" in str(exc_info.value)
        finally:
            asyncio.run(client.aclose())

    def test_deps_context_constructor_allows_serializable_deps(self) -> None:
        """DepsContext constructor should allow serializable deps."""
        from claudecode_model.deps_support import DepsContext

        ctx = DepsContext({"api_key": "secret"})
        assert ctx.deps == {"api_key": "secret"}
