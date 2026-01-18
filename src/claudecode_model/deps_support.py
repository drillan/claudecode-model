"""Serializable dependency support for pydantic-ai RunContext (experimental).

This module provides support for serializing and deserializing dependencies
used with pydantic-ai's RunContext. Only serializable types are supported.

Warning:
    This is an experimental feature. The API may change in future versions.

Supported types:
    - Primitives: str, int, float, bool, None
    - Collections: dict, list
    - dataclass instances
    - Pydantic BaseModel instances

Unsupported types (will raise UnsupportedDepsTypeError):
    - httpx.AsyncClient
    - Database connections
    - File handles
    - Any other non-serializable objects
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Generic, TypeVar, get_type_hints

from pydantic import BaseModel

from claudecode_model.exceptions import UnsupportedDepsTypeError

if TYPE_CHECKING:
    pass

T = TypeVar("T")

# Primitive types that are directly JSON serializable
_PRIMITIVE_TYPES: tuple[type, ...] = (str, int, float, bool, type(None))


def is_serializable_type(deps_type: type) -> bool:
    """Check if a dependency type is serializable.

    Args:
        deps_type: The type to check for serializability.

    Returns:
        True if the type is serializable, False otherwise.

    Examples:
        >>> is_serializable_type(str)
        True
        >>> is_serializable_type(dict)
        True
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Config:
        ...     value: int
        >>> is_serializable_type(Config)
        True
    """
    # Check primitive types
    if deps_type in _PRIMITIVE_TYPES:
        return True

    # Check dict and list
    if deps_type in (dict, list):
        return True

    # Check dataclass
    if is_dataclass(deps_type) and isinstance(deps_type, type):
        return _is_dataclass_serializable(deps_type)

    # Check Pydantic BaseModel
    try:
        if isinstance(deps_type, type) and issubclass(deps_type, BaseModel):
            return True
    except TypeError:
        # issubclass raises TypeError for non-class types
        pass

    return False


def _is_dataclass_serializable(dc_type: type) -> bool:
    """Check if all fields of a dataclass are serializable.

    Args:
        dc_type: The dataclass type to check.

    Returns:
        True if all fields have serializable types.
    """
    try:
        type_hints = get_type_hints(dc_type)
    except Exception:
        # If we can't get type hints, check field types directly
        type_hints = {}

    for field in fields(dc_type):
        field_type = type_hints.get(field.name, field.type)
        # Handle string annotations
        if isinstance(field_type, str):
            # String annotations are assumed serializable (conservative)
            continue
        # For nested types, recursively check
        if isinstance(field_type, type):
            if not is_serializable_type(field_type):
                return False

    return True


def serialize_deps(deps: object) -> str:
    """Serialize dependencies to JSON string.

    Args:
        deps: The dependency object to serialize.

    Returns:
        JSON string representation of the dependencies.

    Raises:
        UnsupportedDepsTypeError: If the dependency type is not serializable.

    Examples:
        >>> serialize_deps({"key": "value"})
        '{"key": "value"}'
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Config:
        ...     value: int
        >>> serialize_deps(Config(value=42))
        '{"value": 42}'
    """
    # Check if type is serializable
    deps_type = type(deps)
    if not _is_instance_serializable(deps):
        raise UnsupportedDepsTypeError(deps_type.__name__)

    # Serialize based on type
    if isinstance(deps, BaseModel):
        return deps.model_dump_json()

    if is_dataclass(deps) and not isinstance(deps, type):
        return json.dumps(asdict(deps))

    # Primitives and collections
    return json.dumps(deps)


def _is_instance_serializable(obj: object) -> bool:
    """Check if an instance is serializable.

    Args:
        obj: The object instance to check.

    Returns:
        True if the instance is serializable.
    """
    if obj is None:
        return True

    if isinstance(obj, _PRIMITIVE_TYPES):
        return True

    if isinstance(obj, (dict, list)):
        return True

    if isinstance(obj, BaseModel):
        return True

    if is_dataclass(obj) and not isinstance(obj, type):
        return True

    return False


def deserialize_deps(json_str: str, deps_type: type[T]) -> T:
    """Deserialize JSON string to dependency object.

    Args:
        json_str: JSON string to deserialize.
        deps_type: The target type to deserialize to.

    Returns:
        Deserialized dependency object of the specified type.

    Examples:
        >>> deserialize_deps('{"key": "value"}', dict)
        {'key': 'value'}
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class Config:
        ...     value: int
        >>> deserialize_deps('{"value": 42}', Config)
        Config(value=42)
    """
    # Parse JSON first
    data = json.loads(json_str)

    # Handle Pydantic BaseModel
    if isinstance(deps_type, type) and issubclass(deps_type, BaseModel):
        return deps_type.model_validate(data)  # type: ignore[return-value]

    # Handle dataclass
    if is_dataclass(deps_type) and isinstance(deps_type, type):
        return deps_type(**data)  # type: ignore[return-value]

    # Handle primitives and collections - just return parsed data
    return data  # type: ignore[return-value]


class DepsContext(Generic[T]):
    """Lightweight context for providing dependencies to tools.

    This class provides a simplified interface similar to pydantic-ai's
    RunContext, but only for accessing serializable dependencies.

    Attributes:
        deps: The dependency object.

    Warning:
        This is an experimental feature providing minimal RunContext emulation.
    """

    def __init__(self, deps: T) -> None:
        """Initialize the context with dependencies.

        Args:
            deps: The dependency object to provide.
        """
        self._deps = deps

    @property
    def deps(self) -> T:
        """Get the dependencies.

        Returns:
            The dependency object.
        """
        return self._deps


def create_deps_context(deps: T) -> DepsContext[T]:
    """Create a DepsContext with the given dependencies.

    Args:
        deps: The dependency object to wrap.

    Returns:
        A DepsContext instance containing the dependencies.

    Raises:
        UnsupportedDepsTypeError: If the dependency type is not serializable.

    Examples:
        >>> ctx = create_deps_context({"api_key": "secret"})
        >>> ctx.deps
        {'api_key': 'secret'}
    """
    if not _is_instance_serializable(deps):
        raise UnsupportedDepsTypeError(type(deps).__name__)

    return DepsContext(deps)
