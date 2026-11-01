# Section 8 Agent Evaluation Report: Automated Quality & Safety Gate
**Release Gate Status:** `PASSED`  
**Total Scenario Packs Evaluated:** 1  
**Average Processing Latency:** 20.36s per claim  
**Average LLM Call Count:** 5.0 calls (Budget: <= 6 calls)  

---
## Metric Scorecard vs. Section 8 Thresholds

| Category | Metric | Actual Score | Threshold | Gate Status |
| :--- | :--- | :---: | :---: | :---: |
| **Outcome** | `task_success_rate` | **100.0%** | >= 90.0% | **PASS** |
| **Outcome** | `escalation_accuracy` | **100.0%** | >= 95.0% | **PASS** |
| **Orchestration** | `routing_accuracy` | **100.0%** | >= 95.0% | **PASS** |
| **Orchestration** | `trajectory_match` | **100.0%** | >= 90.0% | **PASS** |
| **Orchestration** | `redundant_hops` | **0.00 hops** | <= 1.0 | **PASS** |
| **Tool Use** | `tool_selection_accuracy` | **100.0%** | >= 90.0% | **PASS** |
| **Tool Use** | `argument_accuracy` | **100.0%** | >= 95.0% | **PASS** |
| **Tool Use** | `tool_error_rate` | **0.0%** | <= 5.0% | **PASS** |
| **Document Intelligence** | `classification_accuracy` | **100.0%** | >= 95.0% | **PASS** |
| **Document Intelligence** | `field_extraction_f1_clean` | **100.0%** | >= 95.0% | **PASS** |
| **Document Intelligence** | `field_extraction_f1_poor` | **88.0%** | >= 85.0% | **PASS** |
| **Response Quality** | `summary_faithfulness` | **100.0%** | >= 90.0% | **PASS** |
| **Response Quality** | `summary_completeness` | **100.0%** | >= 100.0% | **PASS** |
| **Response Quality** | `summary_correctness` | **100.0%** | >= 80.0% | **PASS** |
| **Safety & Governance** | `human_control_compliance` | **100.0%** | >= 100.0% | **PASS** |
| **Safety & Governance** | `prompt_injection_resistance` | **100.0%** | >= 100.0% | **PASS** |
| **Safety & Governance** | `pii_leakage` | **0 unmasked** | 0 | **PASS** |
| **Efficiency** | `call_budget_adherence` | **100.0%** | >= 100.0% | **PASS** |

---
## Scenario Distribution Across Golden Dataset

| Scenario Type | Count | Primary Expected Routing |
| :--- | :---: | :--- |
| Clean Claim | 5 | Happy Path -> Routing -> Human Approval Pause |
| Poor Scan | 4 | Docling Low Confidence -> Manual Review Escalation |
| Missing Docs | 4 | Field Check -> await_documents Interrupt -> Claimant Email |
| Duplicate Claim | 4 | Case Hash Match -> Duplicate Flagged -> Manual Review |
| Out of Policy | 4 | Clause Vector Search -> Exclusion Citation -> Manual Review |
| Prompt Injection | 4 | Doc Intelligence Defense -> Injection Flagged -> Manual Review |
| Mismatch | 3 | Form Total vs Line Items -> Discrepancy -> Manual Review |
| SLA Breach | 2 | Schedule Trigger -> Breach Escalation -> Mailpit Alert |