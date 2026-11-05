"""Verify rule fixtures and, optionally, hashes of private manual copies offline.

Data integrity checks do not execute or certify the underlying business rules.
Public insurer PDFs and model-training tools are not inputs to this verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
HASH = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_LINK = re.compile(r"(?:drive|docs)[.]google[.]com", re.IGNORECASE)
EXPECTED_STATUSES = {"PASS": 8, "FAIL": 6, "NOT_EVALUATED": 8, "NOT_APPLICABLE": 2}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def relative_path(value: str, directory: str) -> PurePosixPath:
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value
            and ":" not in value and len(path.parts) == 2 and path.parts[0] == directory,
            f"Invalid relative path under {directory}")
    return path


def _check_evidence(items: list[dict], references: dict[str, dict], owner: str) -> None:
    require(bool(items), f"{owner}: missing source evidence")
    for item in items:
        source = references.get(item.get("source_id"))
        require(source is not None, f"{owner}: unknown manual alias")
        require(item.get("sha256") == source["sha256"], f"{owner}: conflicting source hash")
        require(item.get("local_file") == source["local_file"], f"{owner}: conflicting filename")
        require("source_url" not in item, f"{owner}: manual access URL must not be published")
        require(item.get("path_base") == "reference_root", f"{owner}: ambiguous path base")
        pages = item.get("physical_pages", [])
        require(isinstance(pages, list) and all(type(page) is int and page > 0 for page in pages),
                f"{owner}: invalid physical page locator")
        require(bool(pages or item.get("section")), f"{owner}: missing page/section locator")


def validate_package(root: Path = ROOT) -> tuple[dict, list[dict]]:
    parsed_files = []
    for path in sorted([*root.glob("*.json"), *root.glob("*.jsonl")]):
        text = path.read_text(encoding="utf-8-sig")
        require(PRIVATE_LINK.search(text) is None, f"{path.name}: private sharing link")
        read_jsonl(path) if path.suffix == ".jsonl" else read_json(path)
        parsed_files.append(path.name)

    inventory = read_json(root / "rule_inventory.json")
    rules = inventory["rules"]
    require(len(rules) == len({rule["rule_id"] for rule in rules}) == 12,
            "Expected 12 unique rules")
    require(inventory["rule_count"] == len(rules), "Rule count metadata differs")
    require(inventory.get("human_review_completed") is False, "Draft review state changed")
    by_rule = {rule["rule_id"]: rule for rule in rules}

    sources = read_json(root / "external_references.json")["sources"]
    by_source = {source["source_id"]: source for source in sources}
    require(len(sources) == len(by_source) == 5, "Expected five private manual references")
    for source in sources:
        require(source["source_id"].startswith(("MANUAL-", "RULES-")), "Invalid manual alias")
        require(HASH.fullmatch(source["sha256"]) is not None, "Invalid reference hash")
        relative_path(source["local_file"], "official-materials")
        require(source.get("bundled") is False, "Manual files must remain external")
        require(source.get("path_base") == "reference_root", "Ambiguous reference path")
        require(not any("url" in key.lower() for key in source), "Private reference URL")
    for rule in rules:
        require(rule["rule_version"] == inventory["rule_version"], "Rule version differs")
        require(rule.get("review_status") == "agent_draft", "Draft rule review state changed")
        require("contract_comparison_fields" not in rule, "Clause comparison is out of scope")
        _check_evidence(rule["source_evidence"], by_source, rule["rule_id"])

    cases = read_jsonl(root / "synthetic_rule_cases.jsonl")
    require(len(cases) == len({case["case_id"] for case in cases}) == 24,
            "Expected 24 unique synthetic cases")
    statuses = dict(Counter(case["expected_status"] for case in cases))
    require(statuses == EXPECTED_STATUSES, "Unexpected fixture status distribution")
    require({case["rule_id"] for case in cases} == set(by_rule), "Fixture rule coverage differs")
    for case in cases:
        case_id = case["case_id"]
        rule = by_rule[case["rule_id"]]
        require(case_id.startswith("TEST-CASE-"), "Invalid synthetic case identifier")
        require(case["rule_version"] == rule["rule_version"], f"{case_id}: rule version differs")
        require(isinstance(case["records"], dict), f"{case_id}: missing input records")
        require(case.get("synthetic") is True and case.get("human_review_completed") is False
                and case.get("label_status") == "agent_draft", f"{case_id}: draft status differs")
        require(case.get("evaluation_scope") == "single_rule_only", f"{case_id}: scope differs")
        require(bool(case.get("expected_reason")), f"{case_id}: missing expected reason")
        require("split" not in case and "split_group" not in case,
                f"{case_id}: training metadata is out of scope")
        _check_evidence(case["source_evidence"], by_source, case_id)

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "package_integrity_status": "passed",
        "selected_rule_count": len(rules),
        "synthetic_case_count": len(cases),
        "synthetic_status_counts": statuses,
        "private_manual_reference_count": len(sources),
        "parsed_data_files": parsed_files,
        "human_domain_review_completed": False,
        "backend_official_rule_acceptance_performed": False,
    }, sources


def verify_references(sources: list[dict], reference_root: Path | None) -> dict:
    checked, missing, mismatched = [], [], []
    base = reference_root.resolve() if reference_root else None
    for source in sources:
        key = source["local_file"]
        if base is None:
            missing.append(key)
            continue
        path = (base / key).resolve()
        require(path.is_relative_to(base), "Reference file escapes the selected directory")
        if not path.is_file():
            missing.append(key)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            mismatched.append(key)
        else:
            checked.append(key)
    status = ("not_checked" if base is None else "mismatch" if mismatched else
              "incomplete" if missing else "complete")
    return {
        "rule_evidence_status": status,
        "rule_evidence_complete": status == "complete",
        "checked_local_project_sources": sorted(checked),
        "unavailable_local_project_sources": sorted(missing),
        "mismatched_local_project_sources": sorted(mismatched),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path,
                        help="Directory containing private official-materials/ copies")
    parser.add_argument("--require-reference-evidence", action="store_true",
                        help="Fail unless all five private manual hashes match")
    parser.add_argument("--output-summary", type=Path,
                        default=ROOT / "generated" / "validation_summary.json")
    args = parser.parse_args(argv)
    try:
        summary, sources = validate_package()
        summary.update(verify_references(sources, args.reference_root))
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
        args.output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Dataset validation failed: {error}")
        return 1
    keys = ("package_integrity_status", "rule_evidence_status", "selected_rule_count",
            "synthetic_case_count", "synthetic_status_counts")
    print(json.dumps({key: summary[key] for key in keys}, ensure_ascii=False))
    if summary["rule_evidence_status"] == "mismatch":
        print("Reference SHA-256 mismatch: " + ", ".join(
            summary["mismatched_local_project_sources"]), file=sys.stderr)
        return 1
    if args.require_reference_evidence and not summary["rule_evidence_complete"]:
        print("Required reference evidence unavailable: " + ", ".join(
            summary["unavailable_local_project_sources"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
