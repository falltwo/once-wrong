import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function loadSource(relative) {
  const source = await readFile(new URL(relative, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}

const { issueTouchesRow, repeatState, stateLabel, rowValues } =
  await loadSource("../src/utils/issues.ts");
const { evaluationMetrics } = await loadSource("../src/utils/evaluation.ts");

test("live evaluation keeps failures in the full denominator and labels conditional rates", () => {
  const metrics = {
    endToEndHandledCorrectly: { count: 400, total: 595, rate: 0.6723 },
    modelResponseAvailable: { count: 500, total: 595, rate: 0.8403 },
    llmErrors: { count: 95, total: 595, rate: 0.1597 },
    handledCorrectly: { count: 400, total: 500, rate: 0.8 },
  };
  const displayed = evaluationMetrics(metrics);
  assert.equal(displayed[0].key, "endToEndHandledCorrectly");
  assert.equal(displayed[0].metric.total, 595);
  assert.equal(
    displayed.find((item) => item.key === "llmErrors").metric.count,
    95,
  );
  const conditional = displayed.find((item) => item.key === "handledCorrectly");
  assert.equal(conditional.metric.total, 500);
  assert.match(conditional.basis, /排除模型呼叫失敗/);
});

test("legacy evaluation preserves its snapshot without inventing a full-sample score", () => {
  const displayed = evaluationMetrics({
    handledCorrectly: { count: 554, total: 595, rate: 0.9311 },
    llmErrors: { count: 0, total: 595, rate: 0 },
  });
  assert.equal(
    displayed.some((item) => item.key === "endToEndHandledCorrectly"),
    false,
  );
  assert.equal(
    displayed.find((item) => item.key === "llmErrors").metric.count,
    0,
  );
  assert.equal(
    displayed.find((item) => item.key === "handledCorrectly").metric.count,
    554,
  );
});

test("multi-file findings do not attach to the other file's same row number", () => {
  const underwriting = {
    id: "uw:1",
    row: 1,
    fileId: "uw",
    values: { 公司代號: "01" },
  };
  const claim = {
    id: "claim:1",
    row: 1,
    fileId: "claim",
    values: { 公司代號: "01" },
  };
  const finding = {
    cells: [{ row: 1, rowId: "uw:1", fileId: "uw", column: "公司代號" }],
  };
  assert.equal(issueTouchesRow(finding, underwriting), true);
  assert.equal(issueTouchesRow(finding, claim), false);
});

test("a multi-record finding stays visible on every affected row", () => {
  const finding = { cells: [{ rowId: "1" }, { rowId: "2" }] };
  assert.equal(issueTouchesRow(finding, { id: "2", row: 2, values: {} }), true);
  assert.equal(
    issueTouchesRow(finding, { id: "3", row: 3, values: {} }),
    false,
  );
  assert.equal(
    issueTouchesRow(
      { rowId: "A" },
      { id: "A", product: "P", previous: 1, opening: 1 },
    ),
    true,
  );
});

test("regressed is shown independently of the old repeated boolean", () => {
  const finding = { repeated: false, repeatStatus: "regressed" };
  assert.equal(repeatState(finding), "regressed");
  assert.equal(stateLabel(finding), "修好後復發");
  assert.equal(repeatState({ repeated: true }), "repeated");
  assert.equal(repeatState({ repeated: false }), "new");
});

test("generic row values preserve leading zeroes and whitespace", () => {
  const values = { 公司代號: "01", 保單編號序號: "0001", 保單編號: " A00001 " };
  assert.deepEqual(rowValues({ id: "1", row: 1, values }), values);
});

test("uploads distinguish legacy file from complete filing files and preserve errors", async (t) => {
  const { reportsApi } = await loadSource("../src/api/reports.ts");
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, init });
    return new Response(JSON.stringify({ id: "created" }), { status: 201 });
  };
  const underwriting = new File(["synthetic"], "underwriting.csv", {
    type: "text/csv",
  });
  const claim = new File(["synthetic"], "claim.csv", { type: "text/csv" });
  await reportsApi.create("壽險", "2025-10", underwriting);
  assert.equal(requests[0].init.body.get("file").name, "underwriting.csv");
  assert.equal(requests[0].init.body.has("files"), false);
  await reportsApi.upload("report id", [underwriting, claim]);
  assert.deepEqual(
    requests[1].init.body.getAll("files").map((file) => file.name),
    ["underwriting.csv", "claim.csv"],
  );
  assert.equal(requests[1].init.body.has("file"), false);
  assert.match(requests[1].url, /reports\/report%20id\/versions$/);
  await reportsApi.upload("R", [underwriting], true);
  assert.equal(requests[2].init.body.getAll("files").length, 1);
  await reportsApi.evaluation();
  assert.equal(requests[3].init.cache, "no-store");
  assert.match(
    reportsApi.sourceUrl("version id", "file id"),
    /versions\/version%20id\/files\/file%20id\/source$/,
  );
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ message: "檔種重複" }), { status: 422 });
  await assert.rejects(
    reportsApi.upload("R", [underwriting, claim]),
    /檔種重複/,
  );
});
