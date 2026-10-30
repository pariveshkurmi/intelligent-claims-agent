# Intelligent Claims Processing & Case Management Agent

Autonomous multi-agent insurance claims intake, document extraction, coverage verification, and human-in-the-loop approval system built with LangGraph, FastMCP, and PostgreSQL with pgvector.

## Architecture Overview
- **Data Layer:** PostgreSQL 16 + `pgvector`, persistent storage.
- **Protocol Layer:** 4 FastMCP servers (`case-mcp`, `policy-mcp`, `documents-mcp`, `workflow-mcp`).
- **Specialist Agents:** 5 LangChain agents under least privilege.
- **Orchestration:** LangGraph state graph with human approval gate (`interrupt()`).
- **Observability:** Arize Phoenix tracing, Mailpit email mocking.
