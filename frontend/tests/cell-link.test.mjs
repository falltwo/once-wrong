import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";
const { outputText } = ts.transpileModule(
  await readFile(new URL("../src/utils/cellLink.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  },
);
const { cellLinkGeometry } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);
test("the comparison bracket stays inside its selected row", () => {
  const path = cellLinkGeometry(
    { left: 240, top: 160, width: 120, height: 80 },
    { left: 120, top: 160, width: 120, height: 80 },
  );
  assert.equal(path.x, 0);
  assert.equal(path.y, 75);
  assert.ok(path.y < 80);
  assert.match(path.d, /M60 58 V64 H-60 V58/);
});
test("moving a whole row leaves its cell-relative connector unchanged", () => {
  const from = { left: 330, top: 240, width: 130, height: 86 };
  const to = { left: 190, top: 240, width: 140, height: 86 };
  const before = cellLinkGeometry(from, to);
  const moved = cellLinkGeometry(
    { ...from, top: 900, left: from.left + 50 },
    { ...to, top: 900, left: to.left + 50 },
  );
  assert.deepEqual(moved, before);
});
