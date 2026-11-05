"""Reusable synthetic fixtures; no official rule engine is implemented here.

An engine test can request ``rule_case`` and compare its own output with
``expected_status``. Each test receives a copy, so candidate modifications cannot
change another case or the published data.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

DATASET_ROOT = Path(__file__).resolve().parents[1]
_INVENTORY = json.loads((DATASET_ROOT / "rule_inventory.json").read_text(encoding="utf-8-sig"))
_CASES = [
    json.loads(line)
    for line in (DATASET_ROOT / "synthetic_rule_cases.jsonl")
    .read_text(encoding="utf-8-sig")
    .splitlines()
    if line.strip()
]


@pytest.fixture
def rule_inventory() -> dict:
    """The draft rule table, isolated from changes made by a consuming test."""
    return copy.deepcopy(_INVENTORY)


@pytest.fixture
def rule_cases() -> list[dict]:
    """All 24 original synthetic cases, without reading any external documents."""
    return copy.deepcopy(_CASES)


@pytest.fixture(params=_CASES, ids=[case["case_id"] for case in _CASES])
def rule_case(request: pytest.FixtureRequest) -> dict:
    """One synthetic case; its case_id appears in pytest collection and failures."""
    return copy.deepcopy(request.param)


@pytest.fixture
def manual_references() -> dict[str, dict]:
    references = json.loads(
        (DATASET_ROOT / "external_references.json").read_text(encoding="utf-8-sig")
    )
    return {source["source_id"]: source for source in references["sources"]}
