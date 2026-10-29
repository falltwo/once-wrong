"""Business identities for comparing life issues across immutable versions."""

import hashlib
import json

POLICY_KEY_FIELDS = ("公司代號", "保單編號", "保單編號序號")
RECORD_KEY_FIELDS = (*POLICY_KEY_FIELDS, "異動序號", "加保日期")


def life_issue_key(issue: dict, rows: list[dict]) -> str:
    """Keep row coordinates out of history; key-field errors match by policy.

    API issue ids still locate an occurrence within one saved version. Several
    occurrences may share a policy-level history key when the rule checks a key
    field itself, so changing that invalid field cannot hide a repeated problem.
    """
    columns = sorted({cell["column"] for cell in issue["cells"]})
    group_level = bool(set(columns).intersection(RECORD_KEY_FIELDS))
    fields = POLICY_KEY_FIELDS if group_level else RECORD_KEY_FIELDS
    cells = sorted({
        (tuple(rows[cell["row"] - 1]["values"][field] for field in fields), cell["column"])
        for cell in issue["cells"]
    })
    identity = [
        "life_underwriting_v1", issue["ruleId"],
        "group" if group_level else "record", cells,
    ]
    canonical = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return "life-issue-v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
