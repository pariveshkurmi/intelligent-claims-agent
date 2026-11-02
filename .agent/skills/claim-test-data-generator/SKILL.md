---
name: claim-test-data-generator
description: >-
  Generate realistic, copy-paste-ready test datasets and fresh document text files (.txt) for all insurance claim lifecycle scenarios: Clean Claim, Poor Scan, Missing Docs, Duplicate Claim, Prompt Injection, Mismatch, SLA Breach, and Out-of-Policy. Use when creating fresh test cases, preparing document files for claim submission, or validating agent pipelines and guardrails.
---

# Claim Test Data Generator Skill

This skill generates fresh, realistic healthcare insurance test cases and individual document text files (`.txt`) organized into dedicated folders for every claim lifecycle scenario. Each scenario folder contains a copy-paste-ready cheatsheet (`QUICK_SUBMIT.txt`), structured state data (`claim_data.json`), and individual claim documents ready for direct intake testing.

---

## 📁 Generated Test Scenarios Directory Structure

All scenario data is generated under `data/test_scenarios/` (or a customized output directory):

```text
data/test_scenarios/
├── README.md                      # Master index of all generated test scenarios
├── 01_clean_claim/                # Clean Claim (Happy Path Inpatient Appendectomy)
│   ├── QUICK_SUBMIT.txt           # Single-screen copy-paste cheatsheet
│   ├── claim_data.json            # Structured claim payload
│   ├── claim_form.txt             # Primary health claim form (.txt)
│   └── itemized_bill.txt          # Matching hospital itemized bill (.txt)
├── 02_poor_scan/                  # Poor Scan (Degraded OCR / Low Resolution Blur)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   └── poor_scan_claim_form.txt   # Degraded OCR document (conf: 0.42)
├── 03_missing_docs/               # Missing Documents (Claim Form Missing Itemized Bill)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   └── claim_form.txt             # Claim form with explicit missing bill notice
├── 04_duplicate_claim/            # Duplicate Claim (Resubmission Matching CASE-HIST-001)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   ├── duplicate_claim_form.txt
│   └── duplicate_itemized_bill.txt # Resubmission of Invoice #ER-88123 ($1,450.00)
├── 05_prompt_injection/           # Prompt Injection (Adversarial System Override Defense)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   └── prompt_injection_claim_form.txt # Embedded adversarial jailbreak payload
├── 06_mismatch/                   # Mismatch (Name & Amount Discrepancy)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   ├── claim_form.txt             # Patient: Michael Chang ($2,200.00)
│   └── itemized_bill.txt          # Patient: Jonathan Davis ($3,050.00)
├── 07_sla_breach/                 # SLA Breach (Overdue Turnaround > 48h Limit)
│   ├── QUICK_SUBMIT.txt
│   ├── claim_data.json
│   └── urgent_claim_form.txt      # Urgent claim received 74h ago
└── 08_out_of_policy/              # Out of Policy (Cosmetic Surgery Exclusion)
    ├── QUICK_SUBMIT.txt
    ├── claim_data.json
    └── cosmetic_surgery_bill.txt  # Elective Cosmetic Rhinoplasty ($7,500.00)
```

---

## 🚀 How to Generate Fresh Test Data

### Run the Generator Script
You can regenerate brand-new datasets with unique Case IDs and fresh timestamps anytime:

```bash
# Generate fresh test data for all 8 scenarios (default)
python scripts/generate_claim_test_data.py

# Generate with custom case ID prefix
python scripts/generate_claim_test_data.py --prefix CASE-DEMO

# Generate a single targeted scenario (e.g. prompt_injection or mismatch)
python scripts/generate_claim_test_data.py --scenario prompt_injection

# Generate to a custom directory
python scripts/generate_claim_test_data.py --output-dir data/my_custom_scenarios
```

### Script Options
| Flag | Default | Description |
| :--- | :--- | :--- |
| `--output-dir` | `data/test_scenarios` | Directory where scenario folders are created. |
| `--scenario` | `all` | Specific scenario or `all` (`clean_claim`, `poor_scan`, `missing_docs`, `duplicate_claim`, `prompt_injection`, `mismatch`, `sla_breach`, `out_of_policy`). |
| `--prefix` | `CASE-2026` | Case ID prefix. |
| `--static-ids` | `False` | Use deterministic IDs instead of randomized suffixes. |
| `--random-claimants` | `True` | **(Default)** Randomizes claimant names across scenarios from a realistic 20-name pool. |
| `--static-claimants` | `False` | Use fixed canonical names (Sarah Jenkins, Carlos Mendez, etc.). |

> [!NOTE]
> **Special Rule for Duplicate Claim (`04_duplicate_claim`)**:
> Even when random claimants are enabled, the Duplicate Claim scenario intentionally remains pinned to **Robert Langdon** ($1,450.00). This ensures the `IntakeAgent`'s duplicate detection query matches the historical record `CASE-HIST-001` seeded in PostgreSQL. Mismatch scenarios automatically pick two *different* random claimants to guarantee cross-document discrepancy detection.

---

## 📋 How to Submit a Claim in Streamlit

Each scenario folder contains a **`QUICK_SUBMIT.txt`** file formatted specifically for one-click intake:

1. **Open the Scenario Folder**: e.g., `data/test_scenarios/01_clean_claim/`
2. **Open `QUICK_SUBMIT.txt`**: Copy the pre-formatted values:
   - **Case ID**: e.g. `CASE-2026-CLE-101-2143`
   - **Claimant Name**: e.g. `Sarah Jenkins`
   - **Claimant Email**: e.g. `sarah.jenkins@example.com`
   - **Policy ID**: e.g. `POL-UHG-001`
   - **Date of Service**: e.g. `2026-10-15`
   - **Total Claimed Amount**: e.g. `1850.00`
3. **Navigate to the App**: In Streamlit, open **Page 1: Digital Intake (`1_Submit_Claim.py`)**.
4. **Paste the Form Values**: Enter the copied values into the respective fields.
5. **Attach Documents**:
   - **Method A (Drag & Drop)**: Drag the `.txt` file(s) from the scenario folder into the file uploader.
   - **Method B (Copy & Paste)**: Copy document text from `QUICK_SUBMIT.txt` into the Document OCR text areas.
6. **Submit**: Click **🚀 Submit Claim & Launch Agent Workflow**.

---

## 🎯 Scenario Matrix & Expected Pipeline Trajectory

| Scenario | Target Specialist / Gate | Expected Outcome | Key Verification Metric |
| :--- | :--- | :--- | :--- |
| **01 Clean Claim** | Summary / Routing / HITL | `READY_FOR_APPROVAL` | High confidence (>0.95), cites Sec 1.1, routes to Tier 1 Approver |
| **02 Poor Scan** | Document Agent / Guardrails | `MANUAL_REVIEW` | OCR confidence < 0.50 triggers failsafe to human review |
| **03 Missing Docs** | SLA Agent / Comms | `DOCS_PENDING` | Missing bill pauses graph at `await_documents`, dispatches email |
| **04 Duplicate Claim** | Intake Agent / Case MCP | `MANUAL_REVIEW` | Matches `CASE-HIST-001`, flags duplicate warning |
| **05 Prompt Injection** | Document Agent / Security | `MANUAL_REVIEW` | Intercepts adversarial jailbreak, sets `SECURITY_RISK` |
| **06 Mismatch** | Document Join / Summary | `READY_FOR_APPROVAL_RISK_FLAGGED` | Identifies name/amount discrepancies across documents |
| **07 SLA Breach** | SLA Agent / Timers | `ESCALATED` | 74h turnaround exceeds 48h SLA deadline, dispatches alert |
| **08 Out of Policy** | Summary Agent / pgvector | `READY_FOR_APPROVAL_REJECTION_RECOMMENDED` | Retrieves Section 3.1 cosmetic surgery exclusion |

---

## 📚 Technical References
- Detailed scenario specifications: [scenarios_reference.md](./references/scenarios_reference.md)
- Step-by-step submission guide: [sample_submission.md](./examples/sample_submission.md)
- Generator script: [generate_claim_test_data.py](./scripts/generate_claim_test_data.py)

