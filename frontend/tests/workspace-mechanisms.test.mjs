import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";
async function load(path) {
  const { outputText } = ts.transpileModule(
    await readFile(new URL(path, import.meta.url), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    },
  );
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}
const { transitionPipeline } = await load("../src/utils/pipeline.ts");
const { ensureSceneReport, LIFE_SCENE_NAME } = await load(
  "../src/utils/workspaceScenes.ts",
);
test("a fast successful response waits for the spark to reach the pipeline", () => {
  const state = transitionPipeline(
    { stage: "launch", outcome: "pending" },
    "success",
  );
  assert.equal(state.stage, "launch");
  assert.equal(transitionPipeline(state, "arrived").stage, "deposit");
});
test("pending or rejected uploads cannot inject a success particle", () => {
  const waiting = transitionPipeline(
    { stage: "launch", outcome: "pending" },
    "arrived",
  );
  assert.equal(waiting.stage, "waiting");
  assert.equal(transitionPipeline(waiting, "error").stage, "failure");
});
test("switching back to the demo reads the saved report without recreating it", async () => {
  let created = false;
  const result = await ensureSceneReport(
    "demo",
    {
      get: async (id) => ({ id }),
      list: async () => [],
      create: async () => {
        created = true;
      },
    },
    async () => {
      throw new Error("must not load a fixture");
    },
  );
  assert.equal(result.id, "reserve-202609");
  assert.equal(created, false);
});
test("a saved life scene is reused with its existing versions", async () => {
  const report = {
    id: "life-demo",
    name: LIFE_SCENE_NAME,
    period: "2025-10",
    versions: [{ id: "v7" }],
  };
  const result = await ensureSceneReport(
    "life",
    {
      get: async () => {
        throw new Error("unexpected get");
      },
      list: async () => [report],
      create: async () => {
        throw new Error("must not recreate the scene");
      },
    },
    async () => {
      throw new Error("must not load a fixture");
    },
  );
  assert.equal(result, report);
});
test("an absent life scene uploads the labelled synthetic CSV through the existing API", async () => {
  let args;
  const result = await ensureSceneReport(
    "life",
    {
      list: async () => [],
      get: async () => {
        throw new Error("unexpected get");
      },
      create: async (...values) => {
        args = values;
        return { id: "new-scene" };
      },
    },
    async () => "公司代號,保單編號\n01,SYNTHETIC",
  );
  assert.equal(result.id, "new-scene");
  assert.equal(args[0], LIFE_SCENE_NAME);
  assert.equal(args[2].name, "workspace-life-demo.csv");
  assert.match(await args[2].text(), /SYNTHETIC/);
});
