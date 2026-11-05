import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/utils/reportData.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { fixedInVersion } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

const issue = (key) => ({ id: `row:${key}`, issueKey: key, ruleId: "R", title: "", repeated: false });
const versions = (...keysPerVersion) =>
  keysPerVersion.map((keys, index) => ({ number: index + 1, issues: keys.map(issue) }));

test("an error gone from every later version is fixed where it first disappeared", () => {
  assert.equal(fixedInVersion(issue("a"), 1, versions(["a"], ["a"], [], [])), 3);
});

test("an error that came back after a fix is not stamped as fixed", () => {
  assert.equal(fixedInVersion(issue("a"), 1, versions(["a"], [], ["a"])), undefined);
});

test("the latest version, or one whose error is still there, has no fix", () => {
  assert.equal(fixedInVersion(issue("a"), 2, versions(["a"], ["a"])), undefined);
});

test("matching uses the issue key, not the row-based id", () => {
  const moved = { ...issue("a"), id: "other-row:a" };
  assert.equal(fixedInVersion(issue("a"), 1, [{ number: 1, issues: [issue("a")] }, { number: 2, issues: [moved] }]), undefined);
});
