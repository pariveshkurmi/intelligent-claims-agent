"""Governance and Observability: Arize Phoenix and OpenInference Tracing Provider.

Integrates OpenTelemetry OTLP tracing with Arize Phoenix (running on port 6006)
and OpenInference instrumentation for LangChain/LangGraph executions and MCP tool calls.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional
import httpx

logger = logging.getLogger(__name__)

# Configurable endpoints from environment
PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "claims-agent")
PHOENIX_UI_URL = os.getenv("PHOENIX_UI_URL", "http://localhost:6006")
ENABLE_TRACING = os.getenv("ENABLE_PHOENIX_TRACING", "true").lower() in ("true", "1", "yes")

_tracer_provider = None
_tracer = None
_is_initialized = False


def init_tracing(
    project_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    force: bool = False,
) -> bool:
    """
    Initialize Arize Phoenix OpenInference tracer and instrument LangChain.
    Safe to call multiple times (idempotent).
    """
    global _tracer_provider, _tracer, _is_initialized
    if _is_initialized and not force:
        return True

    if not ENABLE_TRACING:
        logger.info("Phoenix tracing is disabled via ENABLE_PHOENIX_TRACING=false.")
        return False

    target_project = project_name or PHOENIX_PROJECT
    target_endpoint = endpoint or os.getenv("PHOENIX_COLLECTOR_ENDPOINT", PHOENIX_ENDPOINT)
    if target_endpoint.startswith("http") and not target_endpoint.endswith("/v1/traces"):
        target_endpoint = f"{target_endpoint.rstrip('/')}/v1/traces"

    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry import trace

        # Register tracer provider with Phoenix collector via HTTP Protobuf protocol
        _tracer_provider = register(
            project_name=target_project,
            endpoint=target_endpoint,
            protocol="http/protobuf",
            batch=False,
            verbose=False,
            set_global_tracer_provider=True,
        )

        # Instrument LangChain and LangGraph executions
        instrumentor = LangChainInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument(tracer_provider=_tracer_provider)

        _tracer = trace.get_tracer(target_project, "0.1.0")
        _is_initialized = True
        logger.info(
            f"Phoenix tracing initialized: project='{target_project}', endpoint='{target_endpoint}'"
        )
        return True
    except Exception as exc:
        logger.warning(
            f"Failed to initialize Phoenix tracing at '{target_endpoint}': {exc}. "
            "Execution will proceed without OpenTelemetry tracing."
        )
        return False


def get_tracer():
    """Get the active OpenTelemetry tracer instance."""
    global _tracer
    if not _is_initialized:
        init_tracing()
    if _tracer is None:
        try:
            from opentelemetry import trace
            _tracer = trace.get_tracer(PHOENIX_PROJECT, "0.1.0")
        except Exception:
            return None
    return _tracer


@contextmanager
def trace_agent_hop(
    agent_name: str,
    case_id: str,
    stage: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Optional[Any], None, None]:
    """Context manager to trace a discrete specialist agent hop in the workflow."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    span_name = f"agent.{agent_name}"
    with tracer.start_as_current_span(span_name) as span:
        try:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("case.id", case_id)
            if stage:
                span.set_attribute("stage.name", stage)
            if metadata:
                for k, v in metadata.items():
                    span.set_attribute(f"agent.metadata.{k}", str(v))
        except Exception:
            pass
        yield span


@contextmanager
def trace_mcp_call(
    server_name: str,
    tool_name: str,
    case_id: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
) -> Generator[Optional[Any], None, None]:
    """Context manager to trace an MCP tool execution hop."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    span_name = f"mcp.{server_name}.{tool_name}"
    with tracer.start_as_current_span(span_name) as span:
        try:
            span.set_attribute("mcp.server", server_name)
            span.set_attribute("mcp.tool", tool_name)
            if case_id:
                span.set_attribute("case.id", case_id)
            if arguments:
                for k, v in arguments.items():
                    val_str = str(v)
                    if len(val_str) > 200:
                        val_str = val_str[:197] + "..."
                    span.set_attribute(f"mcp.argument.{k}", val_str)
        except Exception:
            pass
        yield span


def check_phoenix_health() -> Dict[str, Any]:
    """Check connectivity to the Arize Phoenix tracing container."""
    try:
        resp = httpx.get(PHOENIX_UI_URL, timeout=2.0)
        is_healthy = resp.status_code == 200
        return {
            "status": "connected" if is_healthy else "degraded",
            "status_code": resp.status_code,
            "url": PHOENIX_UI_URL,
            "collector_endpoint": PHOENIX_ENDPOINT,
            "project_name": PHOENIX_PROJECT,
        }
    except Exception as exc:
        return {
            "status": "unreachable",
            "error": str(exc),
            "url": PHOENIX_UI_URL,
            "collector_endpoint": PHOENIX_ENDPOINT,
            "project_name": PHOENIX_PROJECT,
        }


def get_phoenix_spans_count() -> int:
    """Retrieve span count from Phoenix REST API."""
    try:
        resp = httpx.get(f"{PHOENIX_UI_URL}/v1/spans", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            return len(data.get("data", []))
        return 0
    except Exception:
        return 0
