"""Unit tests for the Claim Test Data Generator skill and script."""

import json
import os
import shutil
import tempfile
import pytest

from scripts.generate_claim_test_data import (
    SCENARIO_TEMPLATES,
    format_quick_submit_cheatsheet,
    generate_scenarios,
)


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for scenario generation."""
    temp_dir = tempfile.mkdtemp(prefix="test_claim_scenarios_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_scenario_templates_completeness():
    """Verify that all 8 core scenarios are represented in configurations."""
    scenario_keys = {cfg["scenario_key"] for cfg in SCENARIO_TEMPLATES}
    expected_scenarios = {
        "clean_claim",
        "poor_scan",
        "missing_docs",
        "duplicate_claim",
        "prompt_injection",
        "mismatch",
        "sla_breach",
        "out_of_policy",
    }
    assert expected_scenarios.issubset(scenario_keys)
    assert len(SCENARIO_TEMPLATES) == 8


def test_format_quick_submit_cheatsheet():
    """Test cheatsheet formatting with required Streamlit form fields."""
    cfg = dict(SCENARIO_TEMPLATES[0])
    cfg["claimant_name"] = "Sarah Jenkins"
    cfg["claimant_email"] = "sarah.jenkins@example.com"
    doc_contents = ["UNITEDHEALTHCARE HEALTH CLAIM FORM...", "ST. MARY GENERAL HOSPITAL..."]
    cheatsheet = format_quick_submit_cheatsheet("CASE-2026-TEST-999", cfg, doc_contents)
    assert "CASE-2026-TEST-999" in cheatsheet
    assert "Sarah Jenkins" in cheatsheet
    assert "POL-UHG-001" in cheatsheet
    assert "1850.00" in cheatsheet
    assert "claim_form.txt" in cheatsheet
    assert "itemized_bill.txt" in cheatsheet


def test_generate_all_scenarios_with_random_claimants(temp_output_dir):
    """Test generating scenarios with randomized claimant names."""
    results = generate_scenarios(
        output_base_dir=temp_output_dir,
        target_scenario="all",
        prefix="CASE-UNIT",
        fresh_ids=True,
        random_claimants=True,
    )

    assert len(results) == 8

    # Verify duplicate claim is strictly pinned to Robert Langdon
    assert results["duplicate_claim"]["claimant"] == "Robert Langdon"

    # Verify each folder has required files and updated names in text
    for scen_key, info in results.items():
        folder_path = info["folder"]
        claimant = info["claimant"]
        assert os.path.isdir(folder_path)

        quick_submit_path = os.path.join(folder_path, "QUICK_SUBMIT.txt")
        assert os.path.isfile(quick_submit_path)
        with open(quick_submit_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "STREAMLIT FORM FIELDS" in content
            assert info["case_id"] in content
            assert claimant in content

        json_path = os.path.join(folder_path, "claim_data.json")
        assert os.path.isfile(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["case_id"] == info["case_id"]
            assert data["claimant_name"] == claimant
            assert data["scenario"] == scen_key
            assert len(data["documents"]) > 0

        # Check txt document files
        for f in info["files"]:
            file_path = os.path.join(folder_path, f)
            assert os.path.isfile(file_path)
            assert os.path.getsize(file_path) > 0

    # Verify master README.md exists
    readme_path = os.path.join(temp_output_dir, "README.md")
    assert os.path.isfile(readme_path)
