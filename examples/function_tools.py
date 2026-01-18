#!/usr/bin/env python3
"""Example: Using Function Tools with claudecode-model.

This example demonstrates how to use pydantic-ai's @agent.tool_plain decorator
to create tools that Claude can call during conversation.

Requirements:
    - Claude Code CLI installed and authenticated
    - claudecode-model installed

Usage:
    python examples/function_tools.py
"""

from pydantic_ai import Agent

from claudecode_model import ClaudeCodeModel


def main() -> None:
    """Run the function tools example."""
    # Create model with bypassPermissions for non-interactive execution
    model = ClaudeCodeModel(
        permission_mode="bypassPermissions",
        max_turns=3,
    )

    # Create agent with system prompt
    agent = Agent(
        model,
        system_prompt="You are a helpful assistant with access to weather and calculator tools.",
    )

    # Define tools using @agent.tool_plain decorator
    # Note: tool_plain is used for tools that don't need RunContext

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get the current weather for a city.

        Args:
            city: Name of the city to get weather for.

        Returns:
            Weather information for the specified city.
        """
        # In a real application, you would call a weather API here
        weather_data = {
            "Tokyo": "Sunny, 22°C",
            "New York": "Cloudy, 15°C",
            "London": "Rainy, 12°C",
            "Paris": "Partly cloudy, 18°C",
        }
        return weather_data.get(city, f"Weather data not available for {city}")

    @agent.tool_plain
    def calculate(expression: str) -> str:
        """Calculate a mathematical expression.

        Args:
            expression: Mathematical expression to evaluate (e.g., "2 + 2", "15 * 7").

        Returns:
            The result of the calculation or an error message.
        """
        # WARNING: In production, use a safe expression evaluator
        # This is simplified for demonstration purposes
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "Error: Only basic math operations are allowed"

        try:
            result = eval(expression)  # noqa: S307
            return f"{expression} = {result}"
        except Exception as e:
            return f"Error calculating '{expression}': {e}"

    @agent.tool_plain
    def get_time(timezone: str = "UTC") -> str:
        """Get the current time in a specified timezone.

        Args:
            timezone: Timezone name (e.g., "UTC", "JST", "EST").

        Returns:
            Current time in the specified timezone.
        """
        from datetime import datetime, timezone as tz

        # Simplified timezone handling for demonstration
        now = datetime.now(tz.utc)
        return f"Current time ({timezone}): {now.strftime('%Y-%m-%d %H:%M:%S')} UTC"

    # Run the agent with a prompt that will use the tools
    print("Running agent with function tools...")
    print("-" * 50)

    prompt = """
    I need some information:
    1. What's the weather in Tokyo?
    2. What's 25 * 4?
    3. What time is it now?
    """

    result = agent.run_sync(prompt)

    print("Agent response:")
    print(result.output)


if __name__ == "__main__":
    main()
