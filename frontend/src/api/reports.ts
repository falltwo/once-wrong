import Papa from "papaparse";
import { initialReports } from "../mocks/data";
import { validate } from "../features/validation/rules";
import type { DataRow, Issue, Report, Suggestion } from "../types";

const KEY = "once-wrong-demo-v1";
const pause = () => new Promise((resolve) => setTimeout(resolve, 450));
let cache: Report[] | undefined;
function read(): Report[] {
  if (cache) return structuredClone(cache);
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) {
      const parsed: unknown = JSON.parse(saved);
      if (
        Array.isArray(parsed) &&
        parsed.every(
          (r) =>
            typeof r.id === "string" &&
            Array.isArray(r.versions) &&
            r.versions.length > 0 &&
            r.versions.every(
              (v: { rows?: unknown; issues?: unknown }) =>
                Array.isArray(v.rows) && Array.isArray(v.issues),
            ),
        )
      )
        cache = parsed;
    }
  } catch {
    /* corrupted/unavailable storage: start a fresh demo */
  }
  cache ??= initialReports();
  return structuredClone(cache);
}
function save(reports: Report[]) {
  // Persist before updating memory so failed storage does not report success.
  localStorage.setItem(KEY, JSON.stringify(reports));
  cache = structuredClone(reports);
}
export function download(
  name: string,
  text: string,
  type = "text/plain;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const reportsApi = {
  async list() {
    await pause();
    return read();
  },
  async get(id: string) {
    await pause();
    const result = read().find((r) => r.id === id);
    if (!result) throw new Error("找不到這份報表。");
    return result;
  },
  async upload(reportId: string, file: File) {
    if (!file.name.toLowerCase().endsWith(".csv"))
      throw new Error("目前支援 CSV，請先將 Excel 另存為 CSV UTF-8。");
    if (file.size > 2 * 1024 * 1024)
      throw new Error("檔案超過 2 MB，請使用較小的展示資料。");
    const parsed = Papa.parse<Record<string, string>>(await file.text(), {
      header: true,
      skipEmptyLines: "greedy",
      transformHeader: (h) => h.trim().replace(/^\uFEFF/, ""),
    });
    if (parsed.errors.length)
      throw new Error("CSV 格式不完整，請檢查欄位數量及引號。");
    const columns = ["id", "product", "previous", "opening"];
    if (!columns.every((c) => parsed.meta.fields?.includes(c)))
      throw new Error(
        "缺少必要欄位：id、product、previous、opening。請下載範例參考。",
      );
    if (!parsed.data.length || parsed.data.length > 1000)
      throw new Error("請上傳 1–1,000 筆資料。");
    const ids = new Set<string>();
    const rows: DataRow[] = parsed.data.map((row, index) => {
      const id = row.id?.trim();
      if (!id || ids.has(id))
        throw new Error(
          `第 ${index + 2} 行的 id 空白或重複。每筆資料需要唯一識別碼。`,
        );
      ids.add(id);
      if (!row.previous?.trim() || !row.opening?.trim())
        throw new Error(`第 ${index + 2} 行的金額不可空白。`);
      const previous = Number(row.previous),
        opening = Number(row.opening);
      if (
        !Number.isSafeInteger(previous) ||
        !Number.isSafeInteger(opening) ||
        previous < 0 ||
        opening < 0
      )
        throw new Error(
          `第 ${index + 2} 行的金額須為非負整數（不含千分位逗號）。`,
        );
      return { id, product: row.product?.trim() ?? "", previous, opening };
    });
    await pause();
    const reports = read();
    const report = reports.find((r) => r.id === reportId);
    if (!report) throw new Error("找不到報表。");
    const last = report.versions.at(-1)!;
    const version = {
      id: crypto.randomUUID(),
      number: last.number + 1,
      filename: file.name,
      createdAt: new Date().toISOString(),
      rows,
      issues: validate(rows, last.issues),
    };
    report.versions.push(version);
    report.submittedVersionId = undefined;
    save(reports);
    return version;
  },
  async suggestion(issue: Issue): Promise<Suggestion> {
    await pause();
    if (issue.expected === undefined)
      return {
        source: "demo",
        verification: "unavailable",
        explanation:
          "這筆資料缺少險種代碼。請查閱來源資料補上正確代碼；目前資料不足以提供可靠的修正值。",
      };
    return {
      source: "demo",
      verification: "passed",
      value: issue.expected,
      explanation: `本月期初 ${Number(issue.actual).toLocaleString()} 元，與上月期末 ${issue.expected.toLocaleString()} 元不一致，差額為 ${Math.abs(Number(issue.actual) - issue.expected).toLocaleString()} 元。請核對來源資料後，再修改並上傳。`,
    };
  },
  async submit(reportId: string, versionId: string) {
    await pause();
    const reports = read();
    const report = reports.find((r) => r.id === reportId);
    if (!report) throw new Error("找不到報表。");
    const current = report.versions.at(-1)!;
    if (current.id !== versionId || current.issues.length)
      throw new Error("只有最新且全部檢核通過的版本能確認送出。");
    report.submittedVersionId = current.id;
    save(reports);
  },
};
