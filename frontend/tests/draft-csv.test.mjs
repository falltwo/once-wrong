import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/utils/draftCsv.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { correctedCsv, draftKey } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("demo draft keeps the backend's id column and overlays only drafted cells", () => {
  const rows = [
    { id: "POL-001", product: "CR-01", previous: 100, opening: 100 },
    { id: "POL-004", product: "", previous: 5, opening: 5 },
  ];
  const csv = correctedCsv(rows, ["product", "previous", "opening"], {
    [draftKey("POL-004", "product")]: "CR-04",
  });
  assert.equal(
    csv,
    "﻿id,product,previous,opening\r\nPOL-001,CR-01,100,100\r\nPOL-004,CR-04,5,5\r\n",
  );
});

test("text rows keep leading zeros and quote commas and quotes", () => {
  const rows = [{ id: "1", row: 1, values: { 異動序號: "00001", 備註: 'a,"b"' } }];
  const csv = correctedCsv(rows, ["異動序號", "備註"], { [draftKey("1", "異動序號")]: "00000" });
  assert.equal(csv, '﻿異動序號,備註\r\n00000,"a,""b"""\r\n');
});

test("multi-file filings are not exported as one CSV", () => {
  const rows = [{ id: "f:1", row: 1, fileId: "f", values: { 公司代號: "01" } }];
  assert.equal(correctedCsv(rows, ["公司代號"], {}), null);
});
