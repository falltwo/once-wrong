"""Opt-in live API evaluation using only generated data and a bounded model budget.

Run from the repository root. Raw cases, responses and SQLite evidence stay under
ignored logs/. The key is loaded in memory from .env and is never serialized.
"""

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from once_wrong.database import verify_audit_chain
from once_wrong.main import create_app
from once_wrong.validation import LIFE_COLUMNS

from once_wrong_ai.ai_review.api import issue_ids
from once_wrong_ai.ai_review.llm import LLMError
from once_wrong_ai.ai_review.models import (
    AIFixCandidate,
    ExplanationSource,
    FixSuggestion,
    RejectedSuggestion,
    ReviewItem,
)
from once_wrong_ai.ai_review.openrouter import OpenRouterClient, OpenRouterConfig
from once_wrong_ai.evaluation.cases import make_cases
from once_wrong_ai.evaluation.run import score_item, summary_json
from once_wrong_ai.kb.store import load as load_passages
from once_wrong_ai.report import CellRef
from once_wrong_ai.rules.life import life_field_rules

ROOT = Path(__file__).resolve().parents[1]
TAIPEI = timezone(timedelta(hours=8))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv_bytes(rows, columns=LIFE_COLUMNS):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def code_fingerprint():
    paths = sorted([
        *ROOT.glob("src/**/*.py"), *ROOT.glob("backend/once_wrong/*.py"),
        ROOT / "backend/once_wrong/schema.sql", ROOT / "config/rule_notes.jsonl",
        Path(__file__),
    ])
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


class MeteredClient(OpenRouterClient):
    def __init__(self, config, budget, max_calls, pricing):
        super().__init__(config)
        self.budget, self.max_calls, self.pricing = budget, max_calls, pricing
        self.started = 0
        self.reserved = 0.0
        self.stopped = False
        self.lock = threading.Lock()
        self.responses = []
        self.errors = []
        self._http.event_hooks["response"].append(self.capture)

    def clean_error(self, error):
        return str(error).replace(self.config.api_key, "[REDACTED]")[:400]

    def capture(self, response):
        response.read()
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        choices = body.get("choices") or []
        with self.lock:
            self.responses.append({
                "httpStatus": response.status_code, "returnedModel": body.get("model"),
                "finishReason": choices[0].get("finish_reason") if choices else None,
                "usage": body.get("usage"),
            })

    def explain(self, system_prompt, user_prompt):
        # UTF-8 bytes plus generous framing/schema overhead bound ordinary token
        # input conservatively. Reserve concurrent requests before starting them.
        prompt_bytes = len((system_prompt + user_prompt).encode("utf-8")) + 8000
        upper = (
            prompt_bytes * float(self.pricing["prompt"])
            + self.config.max_tokens * float(self.pricing["completion"])
            + float(self.pricing.get("request") or 0)
        )
        with self.lock:
            if self.started >= self.max_calls or (
                self.usage.cost_usd + self.reserved + upper > self.budget
            ):
                self.stopped = True
                raise LLMError("Live evaluation request/budget limit reached")
            self.started += 1
            self.reserved += upper
        failed = False
        try:
            return super().explain(system_prompt, user_prompt)
        except LLMError as error:
            failed = True
            with self.lock:
                self.errors.append(self.clean_error(error))
            raise
        finally:
            with self.lock:
                # Retain the reservation after uncertain failures rather than
                # assuming a timeout was free. Never automatically retry it.
                if not failed:
                    self.reserved -= upper


def application(path, llm, evaluation_path=None):
    return create_app(
        path, seed_demo=False, llm=llm, knowledge_dir=ROOT / "data/kb",
        memory_path=ROOT / "config/rule_notes.jsonl", evaluation_path=evaluation_path,
    )


def create_report(client, name, raw):
    response = client.post(
        "/reports", data={"name": name, "period": "2025-10"},
        files={"file": ("synthetic-life.csv", raw, "text/csv")},
    )
    if response.status_code != 201:
        raise RuntimeError(f"Upload failed with HTTP {response.status_code}")
    return response.json()


def get_suggestion(client, version, issue_id):
    url = f"/versions/{version['id']}/issues/{quote(issue_id, safe='')}/suggestion"
    response = client.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"Suggestion failed with HTTP {response.status_code}")
    return response.json()


def run_e2e(out, llm):
    path = out / "e2e.sqlite3"
    bad = dict(zip(LIFE_COLUMNS, [
        "01", "SYNTHETIC-REAL-E2E-A", "00001", "00001", "NEW", "20250115", "XED", "00000000"
    ], strict=True))
    good = {**bad, "保單編號": "SYNTHETIC-REAL-E2E-B", "異動序號": "00000"}
    raw = csv_bytes([bad, good])
    with TestClient(application(path, llm)) as client:
        health = client.get("/health").json()
        assert health["ai"]["configured"] and health["ai"]["knowledgeBase"]
        report = create_report(client, "真實模型端到端合成驗收", raw)
        first = report["versions"][0]
        assert len(first["issues"]) == 1
        finding = first["issues"][0]
        assert finding["ruleId"] == "L0302"
        assert client.get(f"/versions/{first['id']}/source").content == raw
        denied = client.post(f"/reports/{report['id']}/submissions", json={"versionId": first["id"]})
        assert denied.status_code == 409
        response = get_suggestion(client, first, finding["id"])
        write_json(out / "e2e-model-response.json", response)
        assert response["model"] == llm.model_name
        assert response["source"] == "ai", "Real model did not produce an adopted explanation"
        assert response["verification"] == "passed" and response["suggestion"]
        rows = [dict(bad), dict(good)]
        for change in response["suggestion"]["changes"]:
            assert change["row"] == 1 and change["column"] == "異動序號"
            rows[change["row"] - 1][change["column"]] = change["value"]
        assert rows[0]["異動序號"] == "00000"
        calls = llm.started
        assert get_suggestion(client, first, finding["id"]) == response
        assert llm.started == calls
        fixed_raw = csv_bytes(rows)
        fixed_response = client.post(
            f"/reports/{report['id']}/versions",
            files={"file": ("fixed.csv", fixed_raw, "text/csv")},
        )
        assert fixed_response.status_code == 201
        fixed = fixed_response.json()
        assert fixed["issues"] == [] and fixed["summary"]["notEvaluatedChecks"] == 0
        assert client.get(f"/reports/{report['id']}").json()["canSubmit"] is True
        assert client.post(
            f"/reports/{report['id']}/submissions", json={"versionId": fixed["id"]}
        ).status_code == 204
        returned_response = client.post(
            f"/reports/{report['id']}/versions",
            files={"file": ("returned.csv", csv_bytes([good, bad]), "text/csv")},
        )
        assert returned_response.status_code == 201
        returned = returned_response.json()
        assert returned["issues"][0]["repeatStatus"] == "regressed"
        assert returned["issues"][0]["prevSeenNumber"] == 1
        assert returned["issues"][0]["fixedInNumber"] == 2
        assert returned["issues"][0]["issueKey"] == finding["issueKey"]
        assert client.post(
            f"/reports/{report['id']}/submissions", json={"versionId": fixed["id"]}
        ).status_code == 409
        stored = client.get(f"/reports/{report['id']}").json()
        assert stored["versions"][0] == first and stored["canSubmit"] is False
    with TestClient(application(path, llm)) as client:
        assert get_suggestion(client, first, finding["id"]) == response
        assert llm.started == calls
    with sqlite3.connect(path) as connection:
        assert verify_audit_chain(connection)
        assert connection.execute("SELECT count(*) FROM ai_review").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM confirmations").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    result = {
        "passed": True, "model": llm.model_name, "health": health,
        "reportId": report["id"], "firstVersionId": first["id"],
        "firstIssueId": finding["id"], "fixedVersionId": fixed["id"],
        "returnedVersionId": returned["id"], "response": response,
        "checks": ["upload", "rule_detection", "original_bytes", "error_confirmation_denied",
                   "real_model", "candidate_revalidated", "same_process_cache", "fixed_upload",
                   "internal_confirmation", "regression_after_reordering", "stale_confirmation_denied",
                   "immutable_original", "restart_cache", "normalized_ai_evidence", "audit_chain"],
        "usage": llm.usage.as_dict(),
    }
    write_json(out / "e2e-summary.json", result)
    print(json.dumps({"e2e": "passed", "calls": llm.started,
                      "costUsd": llm.usage.cost_usd}, ensure_ascii=False), flush=True)
    return result


def score_response(case, violation, before, payload, passages):
    if payload["model"] != os.environ["OPENROUTER_MODEL"]:
        raise ValueError("Response model differs from the evaluated configuration")
    source = ExplanationSource(payload["source"])
    fix = None
    if payload.get("suggestion"):
        raw = payload["suggestion"]
        if payload["verification"] != "passed" or raw["verification"] != "passed":
            raise ValueError("Unverified executable suggestion")
        changes = {}
        for change in raw["changes"]:
            ref = CellRef(change["row"], change["column"])
            if ref in changes and changes[ref] != change["value"]:
                raise ValueError("Conflicting executable suggestion targets")
            if ref not in violation.cells or not isinstance(change["value"], str):
                raise ValueError("Executable suggestion escaped the life cell/text boundary")
            changes[ref] = change["value"]
        if not changes:
            raise ValueError("Empty executable suggestion")
        fix = FixSuggestion(changes, raw["reason"])
        after = life_field_rules().check(case.report.with_changes(changes))
        if violation.key in {item.key for item in after}:
            raise ValueError("Executable suggestion left its target violation")
        if {item.key for item in after} - {item.key for item in before}:
            raise ValueError("Executable suggestion introduced a rule violation")
    elif payload["verification"] != "unavailable":
        raise ValueError("Passed verification without an executable suggestion")
    cited = []
    for citation in payload.get("citations", []):
        if citation["id"] not in passages:
            raise ValueError("API returned an unknown KB citation")
        cited.append(passages[citation["id"]])
    rejected = [RejectedSuggestion(None, AIFixCandidate(changes=[], reason=""), why)
                for why in payload["rejectedSuggestions"]]
    item = ReviewItem(
        violation, payload["title"], payload["explanation"], source, fix,
        rejected=rejected, blocked_numbers=payload["blockedNumbers"], sources=cited,
    )
    return score_item(case, item, before)


def run_benchmark(out, llm, workers, e2e):
    path = out / "benchmark.sqlite3"
    rules = life_field_rules()
    passages = {item.id: item for item in load_passages(ROOT / "data/kb")}
    groups = [(seed, [replace(case, case_id=f"s{seed}-{case.case_id}")
                      for case in make_cases(130, seed, 8)]) for seed in (1, 2, 3)]
    all_cases = [(seed, case) for seed, cases in groups for case in cases]
    expected = sum(len(rules.check(case.report)) for _, case in all_cases)
    scores = []
    by_seed = {seed: [] for seed, _ in groups}
    records = []
    lock = threading.Lock()
    started = time.monotonic()
    before_calls = llm.started
    write_json(out / "plan.json", {"cases": len(all_cases), "issues": expected,
                                  "seeds": [1, 2, 3], "workers": workers})
    with TestClient(application(path, llm)) as client:
        def run(entry):
            seed, case = entry
            raw = csv_bytes(case.report.rows, case.report.columns)
            report = create_report(client, case.case_id, raw)
            version = report["versions"][0]
            before = rules.check(case.report)
            mapping = dict(zip(issue_ids(before, str), before, strict=True))
            if set(mapping) != {item["id"] for item in version["issues"]}:
                raise ValueError("API and reference rule findings differ")
            scored, responses = [], []
            for finding in version["issues"]:
                if llm.stopped:
                    raise RuntimeError("Evaluation stopped at its budget/request limit")
                payload = get_suggestion(client, version, finding["id"])
                scored.append(score_response(case, mapping[finding["id"]], before, payload, passages))
                responses.append({"issueId": finding["id"], "response": payload})
            with lock:
                with (out / "api-responses.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"seed": seed, "caseId": case.case_id,
                                             "reportId": report["id"], "responses": responses},
                                            ensure_ascii=False) + "\n")
                with (out / "items.jsonl").open("a", encoding="utf-8") as stream:
                    for item in scored:
                        stream.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
                records.append({"seed": seed, "caseId": case.case_id,
                                "inputSha256": hashlib.sha256(raw).hexdigest(),
                                "cleanSha256": hashlib.sha256(csv_bytes(
                                    case.clean.rows, case.clean.columns)).hexdigest(),
                                "mutation": case.mutation, "issues": len(scored)})
                count = len(records)
                if count == 1 or count % 10 == 0 or count == len(all_cases):
                    print(json.dumps({"casesDone": count, "casesTotal": len(all_cases),
                                      "requests": llm.started, "costUsd": round(llm.usage.cost_usd, 6)},
                                     ensure_ascii=False), flush=True)
            return seed, scored
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(run, entry) for entry in all_cases]
            for future in as_completed(pending):
                seed, result = future.result()
                scores.extend(result)
                by_seed[seed].extend(result)
    if len(scores) != expected or llm.stopped:
        raise RuntimeError("Incomplete evaluation; no final score was published")
    scores.sort(key=lambda item: (item.case_id, item.rule_id, item.rows))
    runs = []
    for seed, group in by_seed.items():
        metrics = summary_json(group, 130, llm.model_name, [])["metrics"]
        runs.append({"seed": seed, "cases": 130, "policies": 8, "violations": len(group),
                     "model": llm.model_name, "handledCorrectly": metrics["handledCorrectly"]})
    result = summary_json(scores, len(all_cases), llm.model_name, runs)
    correct = result["metrics"]["handledCorrectly"]["count"]
    answered = expected - result["metrics"]["llmErrors"]["count"]
    result["metrics"]["endToEndHandledCorrectly"] = {
        "count": correct, "total": expected, "rate": round(correct / expected, 4),
    }
    result["metrics"]["modelResponseAvailable"] = {
        "count": answered, "total": expected, "rate": round(answered / expected, 4),
    }
    result["evaluationProtocol"] = {
        "transport": "FastAPI TestClient through public upload/suggestion endpoints",
        "profile": "life_underwriting_v1", "ruleVersion": "life_field_rules_v1",
        "syntheticOnly": True, "labelsSentToModel": False,
        "policyIdPseudonymization": True, "candidateBoundary": "violation.cells",
        "maxTokens": llm.config.max_tokens, "temperature": llm.config.temperature,
        "reasoning": llm.config.reasoning, "timeoutSeconds": llm.config.timeout,
        "retries": 0, "workers": workers, "budgetUsd": llm.budget,
        "requestedModel": llm.model_name,
        "returnedModels": sorted({item["returnedModel"] for item in llm.responses
                                  if item["returnedModel"]}),
        "kbSha256": hashlib.sha256((ROOT / "data/kb/passages.jsonl").read_bytes()).hexdigest(),
        "codeSha256": code_fingerprint(),
        "generation": {"casesPerSeed": 130, "seeds": [1, 2, 3], "policiesPerCase": 8},
        "comparisonNote": "Same 390 generated cases as the earlier Gemini run; current API masking and cell/profile guards differ. This is not a pure model A/B comparison or detection precision/recall.",
    }
    result["execution"] = {
        "complete": True, "expectedIssues": expected, "scoredIssues": len(scores),
        "benchmarkRequests": llm.started - before_calls,
        "elapsedSeconds": round(time.monotonic() - started, 2),
        "usageIncludingE2E": llm.usage.as_dict(), "e2eModelRequests": before_calls,
        "errors": llm.errors,
    }
    with sqlite3.connect(path) as connection:
        assert verify_audit_chain(connection)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT count(*) FROM ai_review").fetchone()[0] == expected
    result["execution"]["databaseChecks"] = {
        "auditChain": True, "foreignKeys": True, "aiEvidenceCount": expected,
    }
    write_json(out / "summary.json", result)
    write_json(out / "case-manifest.json", sorted(records, key=lambda item: item["caseId"]))
    print(json.dumps({"complete": True, "model": llm.model_name,
                      "metrics": result["metrics"], "usage": llm.usage.as_dict()},
                     ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--budget-usd", type=float, default=1.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--e2e-only", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    load_dotenv(ROOT / ".env", override=True)
    os.environ["OPENROUTER_MAX_TOKENS"] = "2048"
    config = OpenRouterConfig.from_env()
    os.environ["OPENROUTER_MODEL"] = config.model
    import httpx
    with httpx.Client(timeout=20) as client:
        models = client.get("https://openrouter.ai/api/v1/models")
        models.raise_for_status()
        model = next(item for item in models.json()["data"] if item["id"] == config.model)
    out = args.out or ROOT / "logs/live-evaluation" / datetime.now(TAIPEI).strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    llm = MeteredClient(config, args.budget_usd, 650, model["pricing"])
    write_json(out / "configuration.json", {
        "model": config.model, "maxTokens": config.max_tokens,
        "pricingAtStart": model["pricing"], "budgetUsd": args.budget_usd,
        "maxRequests": 650, "generatedAt": datetime.now(TAIPEI).isoformat(),
        "codeSha256": code_fingerprint(),
    })
    print(json.dumps({"output": str(out), "model": config.model,
                      "budgetUsd": args.budget_usd}, ensure_ascii=False), flush=True)
    try:
        e2e = run_e2e(out, llm)
        if not args.e2e_only:
            run_benchmark(out, llm, args.workers, e2e)
        write_json(out / "request-metadata.json", llm.responses)
    except Exception as error:
        write_json(out / "failed.json", {"complete": False, "errorType": type(error).__name__,
                                         "error": llm.clean_error(error),
                                         "usage": llm.usage.as_dict()})
        print(json.dumps({"complete": False, "errorType": type(error).__name__,
                          "error": llm.clean_error(error)}, ensure_ascii=False), flush=True)
        return 1
    finally:
        write_json(out / "request-metadata.json", llm.responses)
        llm._http.close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(main())
