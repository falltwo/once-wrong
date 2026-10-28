// Development-only browser smoke: uploads synthetic fixtures and records an internal confirmation.
// It deliberately preserves the database; every run creates three new versions.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const here = path.dirname(fileURLToPath(import.meta.url));
const appBase = (process.env.SMOKE_APP_URL || "http://127.0.0.1:5173").replace(/\/+$/, "");
const apiBase = (process.env.SMOKE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const artifacts = process.env.SMOKE_ARTIFACT_DIR || path.join(here, ".smoke-artifacts");
const reportId = "reserve-202609";
const fixtures = path.resolve(here, "../tests/fixtures");
await fs.mkdir(artifacts, { recursive: true });

async function apiReport() {
  const response = await fetch(`${apiBase}/reports/${reportId}`);
  assert.equal(response.status, 200, "seed report must exist");
  return response.json();
}

const before = await apiReport();
const browser = await chromium.launch({
  headless: true,
  ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}),
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
const page = await context.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.setDefaultTimeout(15000);

async function upload(name) {
  await page.getByRole("button", { name: "上傳修正版", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.locator('input[type="file"]').setInputFiles(path.join(fixtures, name));
  const responsePromise = page.waitForResponse((response) =>
    response.url() === `${apiBase}/reports/${reportId}/versions` && response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "上傳並檢核", exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 201, "upload must return a completed Version");
  const version = await response.json();
  await dialog.waitFor({ state: "hidden" });
  assert.equal(version.validationStatus, "completed");
  assert.equal(version.summary.totalChecks, 12);
  assert.equal(version.summary.notEvaluatedChecks, 0);
  return version;
}

try {
  await page.goto(`${appBase}/reports`);
  await page.getByRole("heading", { name: "報表工作空間", exact: true }).waitFor();
  await page.getByRole("link").filter({ has: page.getByRole("heading", { name: "準備金月報", exact: true }) }).click();
  await page.getByRole("button", { name: "上傳修正版", exact: true }).waitFor();

  const firstErrors = await upload("sample-errors.csv");
  assert.equal(firstErrors.issues.length, 2);
  assert.equal(firstErrors.summary.failedChecks, 2);
  await page.getByRole("button", { name: "查看 POL-003 R-07 錯誤", exact: true }).click();
  await page.getByText("固定範本 · 非 AI", { exact: true }).waitFor();
  await page.getByText("目前未提供經重驗的修正值，請核對來源資料。", { exact: true }).waitFor();
  assert.equal(await page.locator(".verified").count(), 0, "unavailable suggestions must never show verification passed");

  const repeatedErrors = await upload("sample-errors.csv");
  assert.equal(repeatedErrors.issues.length, 2);
  assert.ok(repeatedErrors.issues.every((issue) => issue.repeated));
  await page.getByRole("button", { name: "重複錯誤", exact: true }).click();
  assert.equal(await page.locator("tbody tr").count(), 2);
  await page.screenshot({ path: path.join(artifacts, "repeated-errors.png"), fullPage: true });

  const fixed = await upload("sample-fixed.csv");
  assert.equal(fixed.issues.length, 0);
  assert.equal(fixed.summary.passedChecks, 12);
  const confirm = page.getByRole("button", { name: "確認送出（內部紀錄）", exact: true });
  await confirm.waitFor();
  assert.ok(await confirm.isEnabled(), "server canSubmit must enable latest complete version");
  await confirm.click();
  const submissionPromise = page.waitForResponse((response) =>
    response.url() === `${apiBase}/reports/${reportId}/submissions` && response.request().method() === "POST",
  );
  await page.getByRole("dialog").getByRole("button", { name: "已核對，記錄確認", exact: true }).click();
  assert.equal((await submissionPromise).status(), 204);
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  assert.ok(await page.getByRole("button", { name: "已內部確認", exact: true }).isDisabled());

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下載報告", exact: true }).click();
  const download = await downloadPromise;
  const reportPath = path.join(artifacts, download.suggestedFilename());
  await download.saveAs(reportPath);
  const exported = JSON.parse(await fs.readFile(reportPath, "utf8"));
  assert.equal(exported.mode, "backend-demo");
  assert.equal(exported.versionId, fixed.id);
  assert.equal(exported.sourceSha256, fixed.sourceSha256);
  assert.equal(exported.summary.totalChecks, 12);
  assert.equal(exported.internallyConfirmed, true);
  await page.screenshot({ path: path.join(artifacts, "confirmed-version.png"), fullPage: true });

  await page.getByRole("combobox", { name: "選擇報表版本", exact: true }).selectOption(repeatedErrors.id);
  assert.ok(await page.getByRole("button", { name: "確認送出（內部紀錄）", exact: true }).isDisabled());
  await page.reload();
  await page.getByRole("button", { name: "查看 POL-003 R-07 錯誤", exact: true }).waitFor();
  await page.getByRole("link", { name: /查看紀錄/ }).click();
  await page.getByRole("heading", { name: "檢核報告與版本紀錄", exact: true }).waitFor();
  await page.screenshot({ path: path.join(artifacts, "version-history.png"), fullPage: true });

  const after = await apiReport();
  assert.equal(after.versions.length, before.versions.length + 3);
  assert.equal(after.submittedVersionId, fixed.id);
  assert.equal(after.canSubmit, false);
  assert.deepEqual(after.versions.slice(0, before.versions.length), before.versions, "older versions must remain immutable");
  assert.deepEqual(browserErrors, []);
  console.log(JSON.stringify({
    ok: true,
    createdVersions: [firstErrors.id, repeatedErrors.id, fixed.id],
    submittedVersionId: after.submittedVersionId,
    downloadedReport: reportPath,
    artifacts,
    browserErrors,
  }, null, 2));
} finally {
  await browser.close();
}
