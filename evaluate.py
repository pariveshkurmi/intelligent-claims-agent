"""CLI Entrypoint and Automated CI Release Gate for Section 8 Agent Evaluation.

Usage:
    python evaluate.py [--scenario clean_claim] [--limit 10] [--ci] [--output report.md]
"""

import argparse
import json
import os
import sys
from src.evaluation.evaluator import Section8Evaluator


def main():
    parser = argparse.ArgumentParser(
        description="Run automated Section 8 evaluation gate for Claims Multi-Agent system."
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Filter evaluation to a specific scenario (e.g., clean_claim, prompt_injection, poor_scan)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of test cases to evaluate",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run in CI release gate mode: exit with code 1 if any threshold fails",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/evaluation_report.md",
        help="Path to write the markdown evaluation report",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        default=None,
        help="Optional path to write raw JSON evaluation results",
    )

    args = parser.parse_args()

    print("======================================================================")
    print("  STARTING SECTION 8 AUTOMATED EVALUATION GATE")
    print("======================================================================")
    scenarios = [args.scenario] if args.scenario else None
    evaluator = Section8Evaluator()

    results = evaluator.run_evaluation(scenarios=scenarios, limit=args.limit)
    report_md = evaluator.generate_markdown_report(results)

    # Print markdown summary report to console
    print("\n" + report_md + "\n")

    # Save markdown report if path provided
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"--> Saved evaluation report to: {args.output}")

    # Save JSON results if requested
    if args.json_output:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_output)), exist_ok=True)
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"--> Saved JSON results to: {args.json_output}")

    is_passing = results.get("is_passing_release_gate", False)
    if is_passing:
        print("\n[SUCCESS] RELEASE GATE: ALL SECTION 8 METRICS PASSED!")
        sys.exit(0)
    else:
        print("\n[FAILURE] RELEASE GATE: ONE OR MORE METRICS FAILED THRESHOLDS!")
        if args.ci:
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()

