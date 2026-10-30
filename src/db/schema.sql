-- Enable Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. POLICIES Table
CREATE TABLE IF NOT EXISTS policies (
    policy_number VARCHAR(64) PRIMARY KEY,
    product_name VARCHAR(128) NOT NULL,
    policyholder_name VARCHAR(128) NOT NULL,
    effective_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    deductible NUMERIC(10, 2) NOT NULL DEFAULT 1000.00,
    out_of_pocket_max NUMERIC(10, 2) NOT NULL DEFAULT 5000.00,
    co_insurance_rate NUMERIC(4, 2) NOT NULL DEFAULT 0.20,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. POLICY_CLAUSES Table (Vector Storage)
CREATE TABLE IF NOT EXISTS policy_clauses (
    clause_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number VARCHAR(64) NOT NULL REFERENCES policies(policy_number) ON DELETE CASCADE,
    section_number VARCHAR(64) NOT NULL,
    clause_title VARCHAR(256) NOT NULL,
    clause_text TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS policy_clauses_embedding_idx 
ON policy_clauses USING hnsw (embedding vector_cosine_ops);

-- 3. STAFF Table (Adjusters & Approvers with Limit Tiers)
CREATE TABLE IF NOT EXISTS staff (
    staff_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    role VARCHAR(64) NOT NULL, -- 'adjuster', 'approver', 'supervisor'
    email VARCHAR(128) NOT NULL UNIQUE,
    active_cases INT NOT NULL DEFAULT 0,
    approval_limit NUMERIC(12, 2) NOT NULL DEFAULT 0.00
);

-- 4. SLA_RULES Table
CREATE TABLE IF NOT EXISTS sla_rules (
    rule_id VARCHAR(64) PRIMARY KEY,
    tier_name VARCHAR(64) NOT NULL,
    max_turnaround_hours INT NOT NULL,
    missing_docs_wait_days INT NOT NULL DEFAULT 7,
    escalation_threshold_hours INT NOT NULL
);

-- 5. CASES Table (Master Claim Lifecycle Record)
CREATE TABLE IF NOT EXISTS cases (
    case_id VARCHAR(64) PRIMARY KEY,
    policy_id VARCHAR(64) REFERENCES policies(policy_number),
    claimant_name VARCHAR(128) NOT NULL,
    status VARCHAR(64) NOT NULL DEFAULT 'NEW',
    total_amount NUMERIC(12, 2) DEFAULT 0.00,
    assigned_adjuster_id VARCHAR(64) REFERENCES staff(staff_id),
    assigned_approver_id VARCHAR(64) REFERENCES staff(staff_id),
    human_decision VARCHAR(64), -- APPROVED, REJECTED, INFO_REQUESTED
    decision_rationale TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS cases_status_idx ON cases(status);
CREATE INDEX IF NOT EXISTS cases_policy_id_idx ON cases(policy_id);

-- 6. CASE_SUMMARIES Table (1-to-1 with CASES)
CREATE TABLE IF NOT EXISTS case_summaries (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id VARCHAR(64) NOT NULL UNIQUE REFERENCES cases(case_id) ON DELETE CASCADE,
    facts JSONB DEFAULT '{}'::jsonb,
    evidence JSONB DEFAULT '{}'::jsonb,
    missing_info TEXT[] DEFAULT '{}',
    risks JSONB DEFAULT '[]'::jsonb,
    policy_citations JSONB DEFAULT '[]'::jsonb,
    next_action TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. CASE_DOCUMENTS Table
CREATE TABLE IF NOT EXISTS case_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id VARCHAR(64) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    file_path VARCHAR(512) NOT NULL,
    doc_type VARCHAR(64),
    ocr_text TEXT,
    ocr_confidence DOUBLE PRECISION DEFAULT 1.0,
    extracted_fields JSONB DEFAULT '{}'::jsonb,
    is_injection_flagged BOOLEAN DEFAULT FALSE,
    validation_status VARCHAR(64) DEFAULT 'PENDING',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS case_documents_case_id_idx ON case_documents(case_id);

-- 8. CASE_TIMELINE_AUDIT Table (Append-Only)
CREATE TABLE IF NOT EXISTS case_timeline_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    case_id VARCHAR(64) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    before_state JSONB DEFAULT '{}'::jsonb,
    after_state JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS case_timeline_audit_case_id_idx ON case_timeline_audit(case_id);
