"""Tool Retry Middleware: Provides exponential backoff for transient errors."""

import functools
import inspect
import time
from typing import Callable, Any, Tuple, Type


class ToolRetryMiddleware:
    """Wraps tool invocations with retry logic and exponential backoff."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 0.2,
        backoff_factor: float = 2.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with exponential backoff on retryable exceptions."""
        delay = self.initial_delay
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt == self.max_retries:
                    break
                time.sleep(delay)
                delay *= self.backoff_factor

        raise last_exception

    def wrap_tool(self, tool_func: Callable) -> Callable:
        """Decorator wrapping a tool function with retry resilience."""
        @functools.wraps(tool_func)
        def wrapped(*args, **kwargs) -> Any:
            return self.execute(tool_func, *args, **kwargs)

        try:
            wrapped.__signature__ = inspect.signature(tool_func)
        except Exception:
            pass
        return wrapped
