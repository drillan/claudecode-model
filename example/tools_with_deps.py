#!/usr/bin/env python3
"""Example: Using Serializable Dependencies with Function Tools (Experimental).

This example demonstrates how to use pydantic-ai's @agent.tool decorator
with serializable dependencies. This feature is experimental and the API
may change in future versions.

Requirements:
    - Claude Code CLI installed and authenticated
    - claudecode-model installed

Supported dependency types:
    - Primitives: str, int, float, bool, None
    - Collections: dict, list
    - dataclass instances
    - Pydantic BaseModel instances

Unsupported dependency types (will raise UnsupportedDepsTypeError):
    - httpx.AsyncClient
    - Database connections
    - File handles

Usage:
    python example/tools_with_deps.py
"""

from dataclasses import dataclass

from pydantic import BaseModel

from claudecode_model import (
    UnsupportedDepsTypeError,
    convert_tool_with_deps,
    create_deps_context,
    is_serializable_type,
    serialize_deps,
)


# Example 1: Using dataclass as dependencies
@dataclass(frozen=True)
class ApiConfig:
    """Configuration for API calls."""

    base_url: str
    api_key: str
    timeout: int = 30


def example_dataclass_deps() -> None:
    """Demonstrate using dataclass as dependencies."""
    print("\n" + "=" * 50)
    print("Example 1: Dataclass Dependencies")
    print("=" * 50)

    # Check if type is serializable
    print(f"ApiConfig is serializable: {is_serializable_type(ApiConfig)}")

    # Create config instance
    config = ApiConfig(
        base_url="https://api.example.com",
        api_key="secret-key-123",
        timeout=60,
    )

    # Serialize to JSON
    json_str = serialize_deps(config)
    print(f"Serialized: {json_str}")

    # Create DepsContext
    ctx = create_deps_context(config)
    print(f"DepsContext created: {ctx.deps}")
    print(f"  base_url: {ctx.deps.base_url}")
    print(f"  api_key: {ctx.deps.api_key}")


# Example 2: Using Pydantic BaseModel as dependencies
class UserSettings(BaseModel):
    """User settings using Pydantic."""

    username: str
    preferences: dict[str, str]
    max_results: int = 10


def example_pydantic_deps() -> None:
    """Demonstrate using Pydantic BaseModel as dependencies."""
    print("\n" + "=" * 50)
    print("Example 2: Pydantic BaseModel Dependencies")
    print("=" * 50)

    # Check if type is serializable
    print(f"UserSettings is serializable: {is_serializable_type(UserSettings)}")

    # Create settings instance
    settings = UserSettings(
        username="alice",
        preferences={"theme": "dark", "language": "en"},
        max_results=20,
    )

    # Serialize to JSON
    json_str = serialize_deps(settings)
    print(f"Serialized: {json_str}")

    # Create DepsContext
    ctx = create_deps_context(settings)
    print(f"DepsContext created: {ctx.deps}")
    print(f"  username: {ctx.deps.username}")
    print(f"  preferences: {ctx.deps.preferences}")


# Example 3: Using dict as dependencies
def example_dict_deps() -> None:
    """Demonstrate using dict as dependencies."""
    print("\n" + "=" * 50)
    print("Example 3: Dict Dependencies")
    print("=" * 50)

    # Simple dict is always serializable
    config = {
        "api_url": "https://api.example.com",
        "retries": 3,
        "debug": True,
    }

    print(f"dict is serializable: {is_serializable_type(dict)}")

    # Serialize
    json_str = serialize_deps(config)
    print(f"Serialized: {json_str}")

    # Create DepsContext
    ctx = create_deps_context(config)
    print(f"DepsContext created: {ctx.deps}")


# Example 4: Handling unsupported types
def example_unsupported_type() -> None:
    """Demonstrate error handling for unsupported types."""
    print("\n" + "=" * 50)
    print("Example 4: Handling Unsupported Types")
    print("=" * 50)

    import httpx

    # httpx.AsyncClient is NOT serializable
    print(
        f"httpx.AsyncClient is serializable: {is_serializable_type(httpx.AsyncClient)}"
    )

    # Attempting to create DepsContext with unsupported type raises error
    client = httpx.AsyncClient()
    try:
        create_deps_context(client)
    except UnsupportedDepsTypeError as e:
        print(f"Expected error: {e}")
    finally:
        # Clean up
        import asyncio

        asyncio.run(client.aclose())


# Example 5: Using DepsContext with tool conversion
def example_tool_with_deps() -> None:
    """Demonstrate converting a tool with dependencies."""
    print("\n" + "=" * 50)
    print("Example 5: Tool with Dependencies")
    print("=" * 50)

    from pydantic_ai import Agent, RunContext

    from claudecode_model import ClaudeCodeModel

    # Create model
    model = ClaudeCodeModel(
        permission_mode="bypassPermissions",
        max_turns=1,
    )

    # Create agent with dependency type
    agent: Agent[ApiConfig] = Agent(model)

    # Define tool that uses RunContext
    # Note: At declaration time, use RunContext[T] annotation
    # At runtime, convert_tool_with_deps injects a DepsContext
    @agent.tool
    def call_api(ctx: RunContext[ApiConfig], endpoint: str) -> str:
        """Call an API endpoint using the configured settings.

        Args:
            ctx: Context containing API configuration.
            endpoint: API endpoint to call.

        Returns:
            Simulated API response.
        """
        config = ctx.deps
        return f"Called {config.base_url}/{endpoint} (timeout={config.timeout}s)"

    # Get the tool from agent's internal toolset
    tools = list(agent._function_toolset.tools.values())
    print(f"Found {len(tools)} tool(s)")

    if tools:
        tool = tools[0]
        print(f"Tool name: {tool.tool_def.name}")
        print(f"Tool takes_ctx: {tool.takes_ctx}")

        # Create config for the tool
        config = ApiConfig(
            base_url="https://api.example.com",
            api_key="demo-key",
            timeout=30,
        )

        # Convert tool with dependencies
        sdk_tool = convert_tool_with_deps(tool, config)
        print(f"Converted to SdkMcpTool: {sdk_tool.name}")
        print(f"Input schema: {sdk_tool.input_schema}")


# Example 6: Nested dataclass dependencies
@dataclass(frozen=True)
class DatabaseConfig:
    """Database configuration."""

    host: str
    port: int
    name: str


@dataclass(frozen=True)
class AppConfig:
    """Application configuration with nested dataclass."""

    app_name: str
    database: DatabaseConfig
    debug: bool = False


def example_nested_deps() -> None:
    """Demonstrate nested dataclass dependencies."""
    print("\n" + "=" * 50)
    print("Example 6: Nested Dataclass Dependencies")
    print("=" * 50)

    # Nested dataclass is serializable
    print(f"AppConfig is serializable: {is_serializable_type(AppConfig)}")

    # Create nested config
    config = AppConfig(
        app_name="MyApp",
        database=DatabaseConfig(host="localhost", port=5432, name="mydb"),
        debug=True,
    )

    # Serialize (nested structures are flattened to JSON)
    json_str = serialize_deps(config)
    print(f"Serialized: {json_str}")

    # Create DepsContext
    ctx = create_deps_context(config)
    print(f"DepsContext created: {ctx.deps}")
    print(f"  database.host: {ctx.deps.database.host}")


def main() -> None:
    """Run all examples."""
    print("Serializable Dependencies Examples (Experimental)")
    print("=" * 50)

    example_dataclass_deps()
    example_pydantic_deps()
    example_dict_deps()
    example_unsupported_type()
    example_tool_with_deps()
    example_nested_deps()

    print("\n" + "=" * 50)
    print("All examples completed!")
    print("=" * 50)


if __name__ == "__main__":
    import sys

    from claudecode_model.exceptions import CLIExecutionError

    try:
        main()
    except CLIExecutionError as e:
        print(f"CLI execution failed: {e}", file=sys.stderr)
        sys.exit(1)
