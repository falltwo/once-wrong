import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import ts from "typescript";

async function moduleUrl(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  let { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
  });
  if (outputText.includes('"../../utils/reportData"')) {
    outputText = outputText.replace(
      '"../../utils/reportData"',
      JSON.stringify(await moduleUrl("../src/utils/reportData.ts")),
    );
  }
  for (const specifier of ["react/jsx-runtime", "react", "lucide-react"]) {
    outputText = outputText.replaceAll(
      JSON.stringify(specifier),
      JSON.stringify(import.meta.resolve(specifier)),
    );
  }
  return `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
}
const { VersionStack } = await import(
  await moduleUrl("../src/features/versions/VersionStack.tsx")
);
const version = {
  id: "v1",
  number: 1,
  rows: [],
  issues: [],
  createdAt: "2026-11-04T00:00:00Z",
  validationStatus: "completed",
  summary: {
    totalChecks: 17,
    passedChecks: 14,
    failedChecks: 0,
    notEvaluatedChecks: 3,
  },
};
const render = (item) =>
  renderToStaticMarkup(
    createElement(VersionStack, {
      versions: [item],
      currentId: item.id,
      latestId: item.id,
      onSelect() {},
      soundEnabled: false,
      onToggleSound() {},
    }),
  );
test("an archived volume never labels unchecked rules as all passed", () => {
  const html = render(version);
  assert.doesNotMatch(html, /全過|全部通過/);
  assert.match(html, /3.*未檢查/);
});
test("a pending volume cannot claim every check passed", () => {
  const html = render({
    ...version,
    validationStatus: "pending",
    summary: undefined,
  });
  assert.doesNotMatch(html, /全過|全部通過/);
  assert.match(html, /檢核中|待檢核/);
});
test("a completed volume with no skipped checks can show all passed", () => {
  const html = render({
    ...version,
    summary: { ...version.summary, passedChecks: 17, notEvaluatedChecks: 0 },
  });
  assert.match(html, /全部通過/);
});
