"""Exercise offline validation, including missing and mismatched manual evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DATASET_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = DATASET_ROOT / "verify_dataset.py"


def run_validator(tmp_path: Path, *arguments: str, script: Path = VALIDATOR):
    summary_path = tmp_path / "summary.json"
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.run(
        [sys.executable, str(script), "--output-summary", str(summary_path), *arguments],
        cwd=tmp_path,
        check=False,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    return process, summary_path


def test_default_validation_works_without_original_documents_or_network(tmp_path):
    clean_package = tmp_path / "clean-package"
    clean_package.mkdir()
    for filename in (
        "verify_dataset.py", "rule_inventory.json", "synthetic_rule_cases.jsonl",
        "external_references.json", "source_manifest.json",
    ):
        shutil.copyfile(DATASET_ROOT / filename, clean_package / filename)
    assert not (clean_package / "originals").exists()
    process, summary_path = run_validator(tmp_path, script=clean_package / "verify_dataset.py")
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["package_integrity_status"] == "passed"
    assert summary["selected_rule_count"] == 12
    assert summary["synthetic_case_count"] == 24
    assert summary["rule_evidence_status"] == "not_checked"
    assert summary["rule_evidence_complete"] is False
    assert summary["checked_local_project_sources"] == []
    assert len(summary["unavailable_local_project_sources"]) == 5
    assert summary["backend_official_rule_acceptance_performed"] is False


def test_requiring_manual_evidence_rejects_unavailable_files(tmp_path):
    empty_references = tmp_path / "unavailable-references"
    empty_references.mkdir()
    process, summary_path = run_validator(
        tmp_path, "--reference-root", str(empty_references), "--require-reference-evidence"
    )
    assert process.returncode != 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["rule_evidence_status"] == "incomplete"
    assert summary["rule_evidence_complete"] is False
    assert len(summary["unavailable_local_project_sources"]) == 5


def test_missing_optional_manuals_are_reported_without_claiming_rule_acceptance(tmp_path):
    empty_references = tmp_path / "optional-references"
    empty_references.mkdir()
    process, summary_path = run_validator(tmp_path, "--reference-root", str(empty_references))
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["package_integrity_status"] == "passed"
    assert summary["rule_evidence_status"] == "incomplete"
    assert summary["rule_evidence_complete"] is False
    assert summary["backend_official_rule_acceptance_performed"] is False


def test_provided_manual_hash_mismatch_fails_even_when_evidence_is_optional(
    tmp_path, manual_references
):
    reference_root = tmp_path / "wrong-references"
    for source in manual_references.values():
        path = reference_root / source["local_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"This synthetic file is not the referenced manual.\n")
    process, summary_path = run_validator(tmp_path, "--reference-root", str(reference_root))
    assert process.returncode != 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["rule_evidence_status"] == "mismatch"
    assert summary["rule_evidence_complete"] is False
    assert summary["mismatched_local_project_sources"] == sorted(
        source["local_file"] for source in manual_references.values()
    )
    assert summary["checked_local_project_sources"] == []
    assert summary["unavailable_local_project_sources"] == []
