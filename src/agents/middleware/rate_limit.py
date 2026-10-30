"""Tool Call Limit Middleware: Protects against infinite tool recursion and runaway execution."""

import functools
import inspect
from typing import Callable, Any, Dict, Optional


class ToolCallLimitExceededException(Exception):
    """Raised when an agent node exceeds its maximum allowed tool loop count."""
    pass


class ToolCallLimitMiddleware:
    """Enforces execution budget on agent tool invocations."""

    def __init__(self, max_tool_calls: int = 6):
        self.max_tool_calls = max_tool_calls
        self._counts: Dict[str, int] = {}

    def reset(self, context_id: str):
        """Reset the call counter for a specific execution thread or context."""
        self._counts[context_id] = 0

    def get_count(self, context_id: str) -> int:
        """Return the current tool call count for the given context."""
        return self._counts.get(context_id, 0)

    def check_and_increment(self, context_id: str) -> int:
        """Increment tool call count and verify it does not exceed the limit."""
        current = self._counts.get(context_id, 0) + 1
        self._counts[context_id] = current
        if current > self.max_tool_calls:
            raise ToolCallLimitExceededException(
                f"Execution budget exceeded: context '{context_id}' performed {current} "
                f"tool calls (limit is {self.max_tool_calls}). Halting to prevent runaway execution."
            )
        return current

    def wrap_tool(self, tool_func: Callable, context_getter: Optional[Callable[..., str]] = None) -> Callable:
        """Decorator wrapping a tool function to track invocations against budget."""
        @functools.wraps(tool_func)
        def wrapped(*args, **kwargs) -> Any:
            ctx_id = "default_thread"
            if context_getter:
                try:
                    ctx_id = context_getter(*args, **kwargs)
                except Exception:
                    pass
            elif "case_id" in kwargs:
                ctx_id = str(kwargs["case_id"])
            elif len(args) > 0 and isinstance(args[0], str) and args[0].startswith("CASE-"):
                ctx_id = args[0]

            self.check_and_increment(ctx_id)
            return tool_func(*args, **kwargs)

        try:
            wrapped.__signature__ = inspect.signature(tool_func)
        except Exception:
            pass
        return wrapped
