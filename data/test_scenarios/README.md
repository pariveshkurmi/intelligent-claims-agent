# Insurance Claim Test Data Repository

This repository contains fresh test datasets and documents for validating all 8 claim lifecycle scenarios.

## Available Scenarios

| Folder | Scenario | Fresh Case ID | Claimant | Amount | Expected Outcome | Docs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`01_clean_claim`](./01_clean_claim) | **clean_claim** | `CASE-2026-CLE-101-CB3C` | Sophia Martinez | $1,850.00 | `READY_FOR_APPROVAL` | 2 |
| [`02_poor_scan`](./02_poor_scan) | **poor_scan** | `CASE-2026-POO-102-9911` | Anthony Rossi | $1,200.00 | `MANUAL_REVIEW` | 1 |
| [`03_missing_docs`](./03_missing_docs) | **missing_docs** | `CASE-2026-MIS-103-1B51` | Marcus Vance | $3,400.00 | `DOCS_PENDING` | 1 |
| [`04_duplicate_claim`](./04_duplicate_claim) | **duplicate_claim** | `CASE-2026-DUP-104-3CCC` | Robert Langdon | $1,450.00 | `MANUAL_REVIEW` | 2 |
| [`05_prompt_injection`](./05_prompt_injection) | **prompt_injection** | `CASE-2026-PRO-105-3912` | Hannah Schmidt | $8,900.00 | `MANUAL_REVIEW` | 1 |
| [`06_mismatch`](./06_mismatch) | **mismatch** | `CASE-2026-MIS-106-6803` | Brandon Lee | $2,200.00 | `READY_FOR_APPROVAL_RISK_FLAGGED` | 2 |
| [`07_sla_breach`](./07_sla_breach) | **sla_breach** | `CASE-2026-SLA-107-659E` | Jordan Hayes | $4,100.00 | `ESCALATED` | 1 |
| [`08_out_of_policy`](./08_out_of_policy) | **out_of_policy** | `CASE-2026-OUT-108-9970` | Lucas Silva | $7,500.00 | `READY_FOR_APPROVAL_REJECTION_RECOMMENDED` | 1 |

## How to Submit a Claim

1. Open any scenario folder above (e.g. `01_clean_claim`).
2. Open `QUICK_SUBMIT.txt` to view the form values.
3. Navigate to **Page 1: Digital Intake (`1_Submit_Claim.py`)** in the Streamlit portal.
4. Copy-paste the **Case ID**, **Claimant Name**, **Policy ID**, **Date of Service**, and **Total Amount**.
5. Drag and drop the `.txt` document file(s) into the uploader.
6. Click **🚀 Submit Claim & Launch Agent Workflow**.

---
Generated automatically via `generate_claim_test_data.py`.
