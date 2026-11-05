import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(
  new URL("../src/utils/auditStream.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const { suggestionStreamLines, versionStreamLines, selectionStreamResult } =
  await import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
const review = {
  source: "fallback_llm_error",
  verification: "unavailable",
  citations: [],
  suggestion: null,
};
const text = (lines) => lines.map((line) => line.text).join("\n");

test("selecting an already failed idle request produces a finished failure event", () => {
  const result = selectionStreamResult({
    status: "error",
    fetchStatus: "idle",
  });
  assert.match(text(result.lines), /DETAIL_REQUEST_FAILED/);
  assert.match(text(result.lines), /RETRY_AVAILABLE/);
});
test("selecting a cached response while a refetch is running does not report completion", () => {
  const result = selectionStreamResult({
    status: "success",
    fetchStatus: "fetching",
    data: review,
  });
  assert.equal(result, null);
});

test("fallback explanations never claim AI or retrieval completed", () => {
  const result = text(suggestionStreamLines(review));
  assert.match(result, /RULE_TEXT_READY/);
  assert.doesNotMatch(result, /AI_READY|RAG_FETCH|FIX_RECHECK/);
});
test("demo citations and fixes remain explicitly demo events", () => {
  const result = text(
    suggestionStreamLines({
      ...review,
      verification: "passed",
      citations: [{ id: "LIFE-RULE-DEMO", page: 46 }],
      suggestion: {
        reason: "（示範資料）假設已核對",
        verification: "passed",
        changes: [],
      },
    }),
  );
  assert.match(result, /DEMO_CITATION: p.46/);
  assert.match(result, /DEMO_FIX/);
  assert.doesNotMatch(result, /AI_READY|FIX_RECHECK: PASS|RAG_FETCH/);
});
test("real AI results can report actual citation and verified suggestion", () => {
  const result = text(
    suggestionStreamLines({
      ...review,
      source: "ai",
      verification: "passed",
      citations: [{ id: "real-passage", page: 46 }],
      suggestion: { reason: "核對依據", verification: "passed", changes: [] },
    }),
  );
  assert.match(result, /AI_READY/);
  assert.match(result, /CITATION: p.46/);
  assert.match(result, /FIX_RECHECK: PASS/);
});
test("upload summary separates errors from unevaluated checks without row data", () => {
  const result = text(
    versionStreamLines({
      number: 3,
      validationStatus: "completed",
      rows: [{ id: "PRIVATE_POLICY" }],
      summary: {
        totalChecks: 17,
        passedChecks: 14,
        failedChecks: 0,
        notEvaluatedChecks: 3,
      },
    }),
  );
  assert.match(result, /CHECKS_UNEVALUATED: 3/);
  assert.doesNotMatch(result, /ALL_PASS|PRIVATE_POLICY|AI_READY/);
});
