# End-to-End Walkthrough: Submitting a Fresh Test Claim

This guide demonstrates how to take a generated scenario from this skill and submit it directly through the Streamlit Claim Intake portal (`pages/1_Submit_Claim.py`).

---

## Scenario Example: Clean Claim (`01_clean_claim`)

### Step 1: Open the Generated Scenario Folder
Navigate to:
`data/test_scenarios/01_clean_claim/`

Inside you will see:
- `QUICK_SUBMIT.txt`
- `claim_form.txt`
- `itemized_bill.txt`
- `claim_data.json`

### Step 2: Open `QUICK_SUBMIT.txt`
Open `QUICK_SUBMIT.txt` in your text editor or terminal. You will see:
```text
Case ID:               CASE-2026-CLE-101-2143
Claimant Full Name:    Sarah Jenkins
Claimant Email:        sarah.jenkins@example.com
Policy ID:             POL-UHG-001
Date of Service:       2026-10-15
Total Claimed Amount:  1850.00
```

### Step 3: Enter Fields into the Streamlit Portal
1. Open the Streamlit web app in your browser: `http://localhost:8501`.
2. Navigate to **Page 1: Digital Intake (`1_Submit_Claim.py`)**.
3. Under **Claim Information**, copy-paste the values:
   - **Case ID**: `CASE-2026-CLE-101-2143`
   - **Claimant Full Name**: `Sarah Jenkins`
   - **Claimant Email**: `sarah.jenkins@example.com`
   - **Policy ID**: Select `POL-UHG-001`
   - **Date of Service**: `2026-10-15`
   - **Total Claimed Amount**: `1850.00`

### Step 4: Attach the Supporting Documents
You have two flexible submission options:

#### Option A: Drag and Drop (Recommended)
Drag both files from `data/test_scenarios/01_clean_claim/` into the Streamlit file uploader:
- `claim_form.txt`
- `itemized_bill.txt`

#### Option B: Copy-Paste OCR Text
Copy the text content of `claim_form.txt` and `itemized_bill.txt` directly into the Document 1 and Document 2 text areas on the page.

### Step 5: Launch Workflow Execution
Click **🚀 Submit Claim & Launch Agent Workflow**.

Watch the multi-agent orchestration stream in real time:
1. `intake_agent`: Policy verified & duplicate check passed.
2. `document_worker`: Parallel extraction completed.
3. `document_join`: Consistency validated.
4. `summary_agent`: Clinical facts synthesized with Section 1.1 citation.
5. `routing_agent`: Assigned to Tier 1 Approver.
6. `sla_agent`: 48h deadline scheduled.
7. **HITL Gate**: Workflow pauses at `human_review` with button:
   👉 *Proceed to Approvals Portal to Review and Authorize*.

---

## Verifying Telemetry & Traces

- **Phoenix Tracing UI**: Open `http://localhost:6006` to inspect full LangChain/LangGraph execution spans, tool calls, token latencies, and agent prompts.
- **Mailpit Email Portal**: Open `http://localhost:8025` to inspect automated claimant notifications (e.g., when testing `03_missing_docs` or `07_sla_breach`).
- **Approvals Portal**: Navigate to **Page 4: Approvals (`4_Approvals.py`)** to sign off or reject claims under Golden Rule RBAC policies.

