# Database Entity-Relationship (ER) Diagram: Intelligent Claims System
**Project:** UHG FDE Capstone Project  
**Database Engine:** PostgreSQL 16 with `pgvector` Extension  
**Storage Architecture:** Persistent Host Bind-Mount (`./data/postgres_data`)

---

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
    POLICIES ||--o{ CASES : "covers"
    POLICIES ||--o{ POLICY_CLAUSES : "contains"
    CASES ||--|| CASE_SUMMARIES : "has_one"
    CASES ||--o{ CASE_DOCUMENTS : "contains_many"
    CASES ||--o{ CASE_TIMELINE_AUDIT : "tracks_events"
    STAFF ||--o{ CASES : "assigned_adjuster"
    STAFF ||--o{ CASES : "assigned_approver"
    CASES ||--o{ CHECKPOINTS : "checkpoints_by_case_id"
    SLA_RULES ||--o{ CASES : "governs_timelines"

    POLICIES {
        varchar policy_number PK "e.g. POL-UHG-001"
        varchar product_name "e.g. Choice Plus PPO"
        varchar policyholder_name "Sarah Jenkins"
        date effective_date "2026-01-01"
        date expiry_date "2026-12-31"
        numeric deductible "$1,000.00"
        numeric out_of_pocket_max "$5,000.00"
        numeric co_insurance_rate "0.20 (20%)"
        varchar status "ACTIVE / EXPIRED / SUSPENDED"
    }

    POLICY_CLAUSES {
        uuid clause_id PK "Unique clause identifier"
        varchar policy_number FK "Reference to POLICIES"
        varchar section_number "Section 3"
        varchar clause_title "Exclusions: Cosmetic Procedures"
        text clause_text "Full legal clause wording"
        vector embedding "vector(768) - Cosine distance"
    }

    CASES {
        varchar case_id PK "e.g. CASE-2026-1001"
        varchar policy_id FK "Reference to POLICIES"
        varchar claimant_name "John Doe"
        varchar status "NEW / DOCS_PENDING / READY / APPROVED"
        numeric total_amount "Total claimed amount"
        varchar assigned_adjuster_id FK "Reference to STAFF"
        varchar assigned_approver_id FK "Reference to STAFF"
        varchar human_decision "APPROVED / REJECTED / INFO_REQUESTED"
        text decision_rationale "Reason provided by human approver"
        timestamp created_at "Timestamp of intake"
        timestamp updated_at "Last status change"
    }

    CASE_SUMMARIES {
        uuid summary_id PK "Primary key"
        varchar case_id FK "Unique 1-to-1 reference to CASES"
        jsonb facts "Key facts: admission date, diagnosis"
        jsonb evidence "Document cross-references"
        text[] missing_info "List of missing documents or data"
        jsonb risks "Flagged risks & policy mismatches"
        jsonb policy_citations "Exact clauses cited from pgvector"
        text next_action "Recommended next step"
        timestamp updated_at "Timestamp of generation"
    }

    CASE_DOCUMENTS {
        uuid doc_id PK "Unique document ID"
        varchar case_id FK "Reference to CASES"
        varchar file_path "Local storage path"
        varchar doc_type "claim_form / bill / discharge_summary"
        text ocr_text "Full extracted text from Docling"
        float ocr_confidence "Confidence score: 0.0 to 1.0"
        jsonb extracted_fields "Pydantic structured fields"
        boolean is_injection_flagged "Flag: prompt injection detected"
        varchar validation_status "VALID / INVALID / LOW_CONFIDENCE"
        timestamp uploaded_at "Upload timestamp"
    }

    STAFF {
        varchar staff_id PK "e.g. ADJ-101 / APP-201"
        varchar name "Staff full name"
        varchar role "adjuster / approver / supervisor"
        varchar email "Work email address"
        int active_cases "Current workload count"
        numeric approval_limit "Dollar limit (e.g. $2500, $10000)"
    }

    CASE_TIMELINE_AUDIT {
        bigserial audit_id PK "Auto-incrementing sequence"
        varchar case_id FK "Reference to CASES"
        varchar actor "Agent name or Approver email"
        varchar action "STAGE_TRANSITION / FIELD_UPDATE / DECISION"
        jsonb before_state "State before mutation"
        jsonb after_state "State after mutation"
        timestamp timestamp "Append-only event timestamp"
    }

    SLA_RULES {
        varchar rule_id PK "e.g. SLA-STANDARD / SLA-HIGH-DOLLAR"
        varchar tier_name "Standard / High-Dollar / Urgent"
        int max_turnaround_hours "e.g. 48 hours / 24 hours"
        int missing_docs_wait_days "Grace period (e.g. 7 days)"
        int escalation_threshold_hours "Breach trigger threshold"
    }

    CHECKPOINTS {
        varchar thread_id PK "Mapped to case_id"
        varchar checkpoint_ns "LangGraph namespace"
        varchar checkpoint_id "UUID of checkpoint step"
        varchar parent_checkpoint_id "Previous step UUID"
        bytea checkpoint "Serialized graph execution state"
        jsonb metadata "Node name, step count, writes"
    }
```

---

## 2. Table Data Dictionary & Design Purpose

| Table Name | Primary Key | Foreign Keys | Purpose & Design Rationale |
| :--- | :--- | :--- | :--- |
| **`POLICIES`** | `policy_number` | None | Master policy registry. Stores policyholder details, effective date range, and deductible rules. Used by `policy-mcp: get_policy` and `check_coverage`. |
| **`POLICY_CLAUSES`** | `clause_id` | `policy_number` | Stores clause-by-clause legal text and vector embeddings (`vector(768)`). Enables cosine similarity search ($\iff$) via `policy-mcp: search_policy_wording` for accurate policy citations. |
| **`CASES`** | `case_id` | `policy_id`, `assigned_adjuster_id`, `assigned_approver_id` | Master claim lifecycle record. Tracks status transitions, assigned staff, and final human decisions. Serves as the thread anchor for LangGraph persistence. |
| **`CASE_SUMMARIES`** | `summary_id` | `case_id` (Unique 1:1) | Stores structured AI-generated case summaries (facts, risks, evidence, policy clauses). Read by human approvers in Streamlit before decisioning. |
| **`CASE_DOCUMENTS`** | `doc_id` | `case_id` | Stores raw files, Docling OCR text, layout data, OCR confidence scores, and structured Pydantic fields. Flags malicious prompt injection attempts. |
| **`STAFF`** | `staff_id` | None | Workforce directory. Stores adjuster active case counts (for round-robin workload balancing) and approver authorization dollar limits. |
| **`CASE_TIMELINE_AUDIT`** | `audit_id` | `case_id` | Append-only audit trail. Records every MCP tool mutation, stage transition, and human decision with before/after state snapshots for compliance and replay. |
| **`SLA_RULES`** | `rule_id` | None | SLA matrix defining max turnaround times and escalation thresholds. Exposes the `sla://rules` MCP resource. |
| **`CHECKPOINTS`** | `thread_id, checkpoint_id` | `thread_id` $\to$ `case_id` | LangGraph native persistence table managed by `PostgresSaver`. Stores graph snapshots so paused claims can survive server restarts and resume via `Command(resume=...)`. |
