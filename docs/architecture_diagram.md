# System Architecture Diagram: Intelligent Claims Processing & Case Management Agent
**Project:** UHG FDE Capstone Project  
**Author:** FDE Capstone Team  
**Scope:** Multi-agent orchestration, MCP server protocol layer, human-in-the-loop gating, and persistence.

---

## 1. End-to-End System Architecture

```mermaid
flowchart TD
    subgraph UI["1. Presentation Layer (Streamlit Multipage)"]
        UI_Intake["Claim Intake & Upload<br>• Drag-and-drop files<br>• Initial claim metadata"]
        UI_Queue["Case Queue<br>• Filter by status<br>• Workload & SLA tracking"]
        UI_Workspace["Case Workspace<br>• Live agent streaming<br>• Extracted fields & citations"]
        UI_Approval["Approver Portal<br>• Summary & risk review<br>• Role/Limit check<br>• Command(resume)"]
        UI_Chat["Ask the Supervisor<br>• Q&A over case:// resources"]
    end

    subgraph ORCH["2. Orchestration Layer (LangGraph)"]
        Supervisor["Supervisor Node<br>• Mid-size LLM<br>• Route(next, reason)"]
        Guardrails{"Guardrail Gate<br>• Validate case status<br>• Enforce stage order<br>• Low conf -> manual_review"}
        HITL_Pause["interrupt() Pause Gate<br>• Awaiting human decision<br>• Awaiting missing docs"]
        Send_Fanout["Send Fan-Out Node<br>• Concurrent doc processing"]
        Checkpointer[("PostgresSaver Checkpointer<br>• thread_id = case_id<br>• Replay & restart survival")]
    end

    subgraph AGENTS["3. Specialist Agents Layer (LangChain + Middleware)"]
        direction TB
        IntakeAgent["Intake Agent<br>• Small LLM<br>• Duplicate & coverage check"]
        DocAgent["Document Agent<br>• Local Docling OCR (Free)<br>• 1 Unified Pydantic LLM Call per doc<br>(Classify + Fields + Injection Scan)"]
        SummaryAgent["Summary Agent<br>• Mid-size LLM (1 Call)<br>• Facts, risks & policy citations"]
        RoutingAgent["Routing Agent<br>• Code / Small LLM (1 Call)<br>• Workload match & approver tier"]
        SLACommsAgent["SLA & Comms Agent<br>• MCP Prompt Fill (0-1 Call)<br>• Mailpit dispatch & SLA timers"]
        
        Middleware["Agent Middleware Stack<br>• PIIMiddleware (zero leakage)<br>• ToolCallLimitMiddleware<br>• ToolRetryMiddleware"]
    end

    subgraph MCP["4. Protocol Layer (4 FastMCP Servers - Tools, Resources, Prompts)"]
        MCP_Case["case-mcp<br>• Tools: get_case, list_cases, find_similar_cases, register_case, save_summary<br>• Res: case://{id}, case://{id}/timeline<br>• Prompt: case_summary"]
        MCP_Policy["policy-mcp<br>• Tools: get_policy, check_coverage, search_policy_wording<br>• Res: policy://{num}, policy-wording://{prod}"]
        MCP_Docs["documents-mcp<br>• Tools: list_documents, extract_text, classify_document, extract_fields, validate_case_documents<br>• Res: document://{case_id}/{doc_id}"]
        MCP_Workflow["workflow-mcp<br>• Tools: get_workload, assign_case, request_approval, schedule_sla, send_notification, request_documents<br>• Res: staff://directory, sla://rules<br>• Prompts: claimant_letter, approver_brief"]
    end

    subgraph DATA["5. Storage & Observability Layer"]
        PostgresDB[("PostgreSQL 16 + pgvector<br>• Relational cases, docs, staff<br>• Vectorized policy clauses<br>• Append-only audit table")]
        Phoenix["Arize Phoenix<br>• OpenInference traces<br>• Latency (p95) & token tracking"]
        Mailpit["Mailpit (Mock SMTP)<br>• Claimant letters<br>• SLA breach escalations"]
    end

    %% UI Connections
    UI_Intake -->|Start Case| Supervisor
    UI_Approval -->|Command resume| HITL_Pause
    UI_Chat -.->|Read Context| MCP_Case
    Supervisor -->|Stream Events| UI_Workspace

    %% Orchestration Connections
    Supervisor --> Guardrails
    Guardrails -->|Allowed Next Move| AGENTS
    Guardrails -->|Repeated Errors / Low Conf| HITL_Pause
    DocAgent --> Send_Fanout
    Supervisor <--> Checkpointer
    Checkpointer <--> PostgresDB

    %% Agent to MCP Boundaries (Least Privilege)
    IntakeAgent -->|Talks ONLY via MCP| MCP_Policy
    IntakeAgent -->|Talks ONLY via MCP| MCP_Case
    DocAgent -->|Talks ONLY via MCP| MCP_Docs
    SummaryAgent -->|Talks ONLY via MCP| MCP_Case
    SummaryAgent -->|Talks ONLY via MCP| MCP_Docs
    SummaryAgent -->|Talks ONLY via MCP| MCP_Policy
    RoutingAgent -->|Talks ONLY via MCP| MCP_Workflow
    SLACommsAgent -->|Talks ONLY via MCP| MCP_Workflow

    %% MCP to Database & Services
    MCP_Case --> PostgresDB
    MCP_Policy --> PostgresDB
    MCP_Docs --> PostgresDB
    MCP_Workflow --> PostgresDB
    MCP_Workflow --> Mailpit
    ORCH -.->|Traces & Spans| Phoenix
    AGENTS -.->|Model Traces| Phoenix
```

---

## 2. Key Architecture Principles Enforced

### A. The Golden Rule: "Agents Prepare, People Decide"
* **No Approve Tool:** Notice that in `workflow-mcp`, there is intentionally **no** tool to approve, reject, or settle a claim.
* **LangGraph `interrupt()`:** Execution physically pauses at `HITL_Pause`.
* **Resume via Authorized Token:** Only the Streamlit Approver Portal (`UI_Approval`), after verifying the approver's tier limit, issues a `Command(resume=...)` to finalize the claim.

### B. Protocol Boundary (MCP Only)
* **Zero Direct Agent Chat:** Specialist agents cannot communicate directly with each other. All inter-agent data passing occurs by reading/writing to PostgreSQL through the 4 FastMCP servers.
* **Least Privilege:** Each agent is scoped strictly to its permitted MCP toolset.

### C. Zero Data Loss & Checkpoint Persistence
* State is persisted into PostgreSQL via `PostgresSaver` keyed by `thread_id = case_id`.
* Cases can remain paused for human approval for days, survive complete container restarts, and be replayed from historical checkpoints for compliance audits.

### D. Lean 5–6 LLM Call Budget (Anti-Overcalling Architecture)
* **Single Unified Document Call:** Classification, field extraction, date/amount normalization, and prompt injection detection are executed in **one single Pydantic LLM call per document**.
* **Zero Supervisor Ping-Pong:** LangGraph conditional edges handle predictable hand-offs deterministically; the Supervisor LLM is reserved for genuine branching decisions (missing documents, manual review escalations).
* **Section 8 Compliance:** Directly passes Metric 5 (**Redundant Hops $\le 1$ per case**) and Metric 18 (**Latency & Cost within 10% of baseline**).
