"""Check fixture contracts and provenance, not rule execution or label accuracy."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import PurePosixPath

STATUSES = {"PASS", "FAIL", "NOT_EVALUATED", "NOT_APPLICABLE"}
IDENTIFIER_FIELDS = {"company_id", "product_family", "policy_id", "policy_number", "reference_id"}
DATE_FIELDS = {
    "coverage_start", "coverage_end", "incident_date", "effective_date",
    "payment_date", "annuity_start",
}
MONEY_FIELDS = {
    "first_cancer_amount_ntd", "accidental_death_amount_ntd", "minimum_ntd", "maximum_ntd",
    "guaranteed_amount_original",
}


def _walk_fields(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk_fields(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_fields(item)


def test_table_has_unique_cases_and_covers_every_draft_rule(rule_inventory, rule_cases):
    rules = rule_inventory["rules"]
    rule_ids = [rule["rule_id"] for rule in rules]
    case_ids = [case["case_id"] for case in rule_cases]
    assert len(rules) == len(set(rule_ids)) == rule_inventory["rule_count"] == 12
    assert len(rule_cases) == len(set(case_ids)) == 24
    assert set(case_ids) == {f"TEST-CASE-{number:03d}" for number in range(1, 25)}
    assert {case["rule_id"] for case in rule_cases} == set(rule_ids)
    assert Counter(case["expected_status"] for case in rule_cases) == {
        "PASS": 8, "FAIL": 6, "NOT_EVALUATED": 8, "NOT_APPLICABLE": 2,
    }
    assert rule_inventory["human_review_completed"] is False
    for rule in rules:
        assert rule["rule_version"] == rule_inventory["rule_version"]
        assert rule["review_status"] == "agent_draft"
        assert rule["implementation_status"] == "not_implemented_in_current_backend"
        assert "contract_comparison_fields" not in rule


def test_each_fixture_retains_its_draft_expectation_and_evidence(
    rule_case, rule_inventory, manual_references
):
    rules = {rule["rule_id"]: rule for rule in rule_inventory["rules"]}
    rule = rules[rule_case["rule_id"]]
    assert re.fullmatch(r"TEST-CASE-[0-9]{3}", rule_case["case_id"])
    assert rule_case["base_case_id"].startswith("TEST-BASE-")
    assert rule_case["rule_version"] == rule["rule_version"]
    assert rule_case["expected_status"] in STATUSES
    assert rule_case["expected_reason"].strip()
    assert rule_case["synthetic"] is True
    assert rule_case["label_status"] == "agent_draft"
    assert rule_case["human_review_completed"] is False
    assert rule_case["evaluation_scope"] == "single_rule_only"
    # Missing evidence must remain distinct from a failed or passed evaluation.
    assert bool(rule_case["missing_dependencies"]) == (
        rule_case["expected_status"] == "NOT_EVALUATED"
    )
    assert len(rule_case["missing_dependencies"]) == len(set(rule_case["missing_dependencies"]))
    assert rule_case["source_evidence"] == rule["source_evidence"]
    assert rule_case["source_evidence"]
    for evidence in rule_case["source_evidence"]:
        reference = manual_references[evidence["source_id"]]
        assert re.fullmatch(r"(?:MANUAL|RULES)-[A-Z0-9-]+", evidence["source_id"])
        assert re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"])
        assert evidence["sha256"] == reference["sha256"]
        assert evidence["local_file"] == reference["local_file"]
        relative = PurePosixPath(evidence["local_file"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert evidence["path_base"] == "reference_root"
        assert "source_url" not in evidence
        assert evidence["physical_pages"] or evidence["section"]
        assert all(type(page) is int and page > 0 for page in evidence["physical_pages"])


def test_each_fixture_preserves_synthetic_identifiers_and_lossless_types(rule_case):
    records = rule_case["records"]
    assert {"company_id", "product_family", "policy_id"}.issubset(records)
    for key, value in _walk_fields(records):
        if key in IDENTIFIER_FIELDS:
            assert isinstance(value, str) and value.startswith("TEST-")
        if key in DATE_FIELDS:
            assert isinstance(value, str)
            assert re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
            assert date.fromisoformat(value).isoformat() == value
        if key in MONEY_FIELDS:
            assert isinstance(value, str)
            assert re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
            assert Decimal(value).is_finite() and Decimal(value) >= 0
        if key == "coverage_bitmask_50":
            assert isinstance(value, str) and re.fullmatch(r"[01]{50}", value)
        if key == "policy_sequence":
            assert isinstance(value, str) and re.fullmatch(r"[0-9]{5}", value)
        if key == "benefit_code":
            assert isinstance(value, str) and re.fullmatch(r"[0-9]{3}", value)


def test_life_benefit_enum_links_to_the_field_table_check(rule_inventory):
    rule = next(rule for rule in rule_inventory["rules"]
                if rule["rule_id"] == "LIFE.LFD.benefit_type_current_manual")
    evidence = next(item for item in rule["source_evidence"]
                    if item["source_id"] == "RULES-LIFE-2025")
    assert evidence["source_codes"] == ["D0102"]
    assert 58 in evidence["physical_pages"]
    assert rule["source_ambiguity"]  # The 1–6 / 1–3 conflict remains unresolved.


def test_annuity_conflict_has_a_locator_without_an_invented_engine_code(rule_inventory):
    rule = next(rule for rule in rule_inventory["rules"]
                if rule["rule_id"] == "ANNUITY.GUARANTEE.type_period_conflict")
    evidence = rule["source_evidence"][0]
    assert evidence["source_codes"] == []
    assert evidence["physical_pages"] == [19, 126]
    assert evidence["section"] and evidence["note"]
    assert rule["source_ambiguity"]
