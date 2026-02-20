# claudecode-model

pydantic-ai Model implementation for Claude Code CLI using Claude Agent SDK.

## Installation

```bash
pip install claudecode-model
```

Or with uv:

```bash
uv add claudecode-model
```

### Requirements

- Python 3.13+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated

## Quick Start

### Basic Usage

```python
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

model = ClaudeCodeModel()
agent = Agent(model, system_prompt="You are a helpful assistant.")

result = agent.run_sync("Hello, how are you?")
print(result.output)
```

### With Structured Output

```python
from pydantic import BaseModel
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

class CityInfo(BaseModel):
    name: str
    country: str
    population: int

model = ClaudeCodeModel()
agent = Agent(model, result_type=CityInfo)

result = agent.run_sync("Tell me about Tokyo")
print(result.output)  # CityInfo(name='Tokyo', country='Japan', population=...)
```

## Function Tools

claudecode-model supports pydantic-ai's Function Tools via `@agent.tool_plain` decorator.

### Basic Tool Usage

```python
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

model = ClaudeCodeModel()
agent = Agent(model, system_prompt="You are a helpful assistant.")

@agent.tool_plain
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # In real usage, call a weather API here
    return f"The weather in {city} is sunny, 22°C."

@agent.tool_plain
def calculate(expression: str) -> str:
    """Calculate a mathematical expression.

    WARNING: This demo uses eval() for simplicity.
    In production, use a safe library like `simpleeval` or `asteval`.
    """
    try:
        result = eval(expression)  # UNSAFE: demo only
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"

# Execute with tools
result = agent.run_sync("What's the weather in Tokyo? Also, what's 15 * 7?")
print(result.output)
```

### Tool with Multiple Parameters

```python
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

model = ClaudeCodeModel()
agent = Agent(model)

@agent.tool_plain
def search_products(
    query: str,
    category: str = "all",
    max_price: float | None = None,
) -> str:
    """Search for products in the store."""
    filters = f"category={category}"
    if max_price:
        filters += f", max_price={max_price}"
    return f"Found 5 products matching '{query}' ({filters})"

result = agent.run_sync("Find me headphones under $100")
print(result.output)
```

## Serializable Dependencies (Experimental)

For tools that need access to configuration or context, claudecode-model provides experimental support for serializable dependencies.

### Supported Dependency Types

- Primitives: `str`, `int`, `float`, `bool`, `None`
- Collections: `dict`, `list`
- `dataclass` instances
- Pydantic `BaseModel` instances

### Unsupported Types

- `httpx.AsyncClient`
- Database connections
- File handles
- Any non-serializable objects

### Usage with Dependencies

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from claudecode_model import ClaudeCodeModel, convert_tool_with_deps

@dataclass
class ApiConfig:
    base_url: str
    api_key: str

model = ClaudeCodeModel()
agent: Agent[ApiConfig] = Agent(model)

@agent.tool
def call_api(ctx: RunContext[ApiConfig], endpoint: str) -> str:
    """Call an external API endpoint."""
    config = ctx.deps
    return f"Called {config.base_url}/{endpoint} with key {config.api_key[:4]}..."

# Create config and convert tool with dependencies
config = ApiConfig(base_url="https://api.example.com", api_key="secret-key-123")

# Get tool from agent's internal toolset
tools = list(agent._function_toolset.tools.values())
sdk_tool = convert_tool_with_deps(tools[0], config)

# Use the converted tool with Claude Agent SDK
```

### DepsContext for Manual Context Injection

```python
from claudecode_model import DepsContext, create_deps_context

# Create a context with your dependencies
config = {"api_key": "secret", "timeout": 30}
ctx = create_deps_context(config)

# Access deps
print(ctx.deps["api_key"])  # "secret"
```

## ClaudeCodeModel Configuration

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | `"claude-sonnet-4-5"` | Claude model to use |
| `working_directory` | `str \| None` | `None` | Working directory for CLI execution |
| `timeout` | `float` | `120.0` | Timeout in seconds |
| `allowed_tools` | `list[str] \| None` | `None` | List of allowed CLI tools |
| `disallowed_tools` | `list[str] \| None` | `None` | List of disallowed CLI tools |
| `permission_mode` | `str \| None` | `None` | Permission mode (e.g., "bypassPermissions") |
| `max_turns` | `int \| None` | `None` | Maximum conversation turns |
| `interrupt_handler` | `Callable[[], bool] \| None` | `None` | Callback for Ctrl-C confirmation |

### Model Settings

Pass additional settings via `model_settings` in Agent:

```python
from claudecode_model import ClaudeCodeModel, ClaudeCodeModelSettings

model = ClaudeCodeModel()
settings: ClaudeCodeModelSettings = {
    "timeout": 120.0,
    "max_turns": 5,
    "max_budget_usd": 1.0,
    "append_system_prompt": "Be concise.",
    "working_directory": "/path/to/project",
}

agent = Agent(model, model_settings=settings)
```

## Getting Response Metadata

Use `request_with_metadata` to access full response details:

```python
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from claudecode_model import ClaudeCodeModel

model = ClaudeCodeModel()
messages = [ModelRequest(parts=[UserPromptPart(content="Hello")])]
params = ModelRequestParameters()

result = await model.request_with_metadata(messages, None, params)

# Access metadata (note: total_cost_usd may be None)
cost = result.cli_response.total_cost_usd
print(f"Cost: ${cost if cost is not None else 'N/A'}")
print(f"Turns: {result.cli_response.num_turns}")
print(f"Input tokens: {result.cli_response.usage.input_tokens}")
print(f"Output tokens: {result.cli_response.usage.output_tokens}")
```

## Graceful Exit and Interrupt Handling

claudecode-model handles `KeyboardInterrupt` (Ctrl-C) gracefully, ensuring subprocesses are properly terminated and resources are cleaned up.

### Default Behavior

When a `KeyboardInterrupt` occurs during execution:

1. **SIGTERM** is sent to the subprocess for graceful shutdown
2. Waits up to 5 seconds for the process to exit
3. If still running, **SIGKILL** is sent to force termination
4. A `CLIInterruptedError` is raised with any partial results

```python
from claudecode_model import ClaudeCodeModel, CLIInterruptedError

model = ClaudeCodeModel()
agent = Agent(model)

try:
    result = agent.run_sync("Analyze this large codebase")
except CLIInterruptedError as e:
    print(f"Interrupted: {e}")
```

### Custom Interrupt Handler

Provide a callback via `interrupt_handler` to add confirmation prompts or custom cleanup logic before the process is terminated:

```python
def confirm_exit() -> bool:
    """Return True to proceed with exit, False to continue execution."""
    response = input("\nAre you sure you want to exit? (y/n): ")
    return response.lower() == "y"

model = ClaudeCodeModel(interrupt_handler=confirm_exit)
```

The `interrupt_handler` callback:
- Takes no arguments
- Returns `bool`: `True` to proceed with termination, `False` to continue
- Is called on the first Ctrl-C; a second Ctrl-C always forces immediate termination

## Limitations and Notes

### Function Tools

1. **`@agent.tool` with `takes_ctx=True`**: Only supported with serializable dependencies. Use `@agent.tool_plain` for tools without context.

2. **Internal API Usage**: Tool conversion uses pydantic-ai internal APIs (`agent._function_toolset`) that may change in future versions.

3. **Async Tools**: Both sync and async tools are supported.

### Serializable Dependencies (Experimental)

1. **No Runtime Connections**: Dependencies like `httpx.AsyncClient` or database connections cannot be serialized. Use configuration objects instead.

2. **API Stability**: This feature is experimental and the API may change.

### General

1. **Claude CLI Required**: The Claude Code CLI must be installed and authenticated.

2. **Structured Output**: Supported via `--json-schema` option. Use `result_type` in Agent for automatic schema generation.

## Migration Guide: CLI to SDK

If you were using the CLI subprocess approach, here's how to migrate:

### Before (CLI subprocess)

```python
import subprocess
import json

result = subprocess.run(
    ["claude", "-p", "Hello", "--output-format", "json"],
    capture_output=True,
    text=True,
)
response = json.loads(result.stdout)
```

### After (Claude Agent SDK via claudecode-model)

```python
from pydantic_ai import Agent
from claudecode_model import ClaudeCodeModel

model = ClaudeCodeModel()
agent = Agent(model)
result = agent.run_sync("Hello")
print(result.output)
```

### Key Differences

| Aspect | CLI Subprocess | claudecode-model |
|--------|---------------|------------------|
| Tool Support | Manual JSON handling | `@agent.tool_plain` decorator |
| Structured Output | Manual `--json-schema` | Automatic via `result_type` |
| Error Handling | Exit codes, stderr parsing | Python exceptions |
| Type Safety | None | Full type hints |
| Integration | Low-level | pydantic-ai native |

## API Reference

### Main Classes

- `ClaudeCodeModel`: pydantic-ai Model implementation
- `CLIResponse`: Response data with metadata
- `CLIUsage`: Token usage information

### Agent Toolsets

- `ClaudeCodeModel.set_agent_toolsets(toolsets, *, server_name="pydantic_tools")`: Register pydantic-ai tools as MCP server
  - `server_name`: Customize the MCP server name (appears as `mcp__<server_name>__<tool_name>` in Claude Code CLI)

```python
model = ClaudeCodeModel()
# Default: tools appear as mcp__pydantic_tools__<tool_name>
model.set_agent_toolsets(tools)

# Custom: tools appear as mcp__team__<tool_name>
model.set_agent_toolsets(tools, server_name="team")
```

### Tool Conversion

- `convert_tool(tool)`: Convert pydantic-ai Tool to SdkMcpTool
- `convert_tool_with_deps(tool, deps)`: Convert with dependency injection (experimental)
- `convert_tools_to_mcp_server(tools, ...)`: Create MCP server config

### Dependency Support (Experimental)

- `DepsContext[T]`: Lightweight RunContext emulation
- `create_deps_context(deps)`: Create DepsContext instance
- `is_serializable_type(type)`: Check if a type is serializable
- `is_instance_serializable(obj)`: Check if an instance is serializable
- `serialize_deps(deps)`: Serialize to JSON string
- `deserialize_deps(json_str, type)`: Deserialize from JSON

### Exceptions

- `ClaudeCodeError`: Base exception
- `CLINotFoundError`: Claude CLI executable not found
- `CLIExecutionError`: SDK execution failed
- `CLIInterruptedError`: User interrupted execution (Ctrl-C)
- `CLIResponseParseError`: Response parsing failed
- `UnsupportedDepsTypeError`: Non-serializable dependency type
- `TypeHintResolutionError`: Type hint resolution failed

## License

MIT
