// This adapter always uses the backend. It never reads localStorage or falls back to mocks.
import type {
  BackendHealth,
  Evaluation,
  Issue,
  Report,
  Suggestion,
  Version,
} from "../types";

const env = (
  import.meta as ImportMeta & {
    env?: Record<string, string | boolean | undefined>;
  }
).env;
const configuredBase = env?.VITE_API_BASE_URL;
const API_BASE = (
  typeof configuredBase === "string" && configuredBase.trim()
    ? configuredBase.trim()
    : "/api"
).replace(/\/+$/, "");

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const payload = body as Record<string, unknown>;
  if (typeof payload.message === "string") return payload.message;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.flatMap((item: unknown) => {
      if (!item || typeof item !== "object") return [];
      const detail = item as { loc?: unknown; msg?: unknown };
      if (typeof detail.msg !== "string") return [];
      const location = Array.isArray(detail.loc) ? detail.loc.join(".") : "";
      return [location ? `${location}: ${detail.msg}` : detail.msg];
    });
    if (messages.length) return messages.join("；");
  }
  if (payload.error && typeof payload.error === "object") {
    const nested = payload.error as { message?: unknown };
    if (typeof nested.message === "string") return nested.message;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("無法連線到檢核服務，請確認後端已啟動並允許目前前端來源。");
  }
  // A successful submission intentionally has no JSON response body.
  if (response.status === 204 && response.ok) return undefined as T;
  const text = await response.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    if (response.ok) throw new Error("檢核服務回傳非 JSON 資料。");
  }
  if (!response.ok) {
    throw new Error(
      errorMessage(body, `檢核服務請求失敗（HTTP ${response.status}）。`),
    );
  }
  if (body === undefined) throw new Error("檢核服務沒有回傳預期的資料。");
  return body as T;
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
  health(): Promise<BackendHealth> {
    return request<BackendHealth>("/health");
  },
  evaluationLatest(): Promise<Evaluation> {
    return request<Evaluation>("/evaluations/latest", { cache: "no-store" });
  },
  list(): Promise<Report[]> {
    return request<Report[]>("/reports");
  },
  get(id: string): Promise<Report> {
    return request<Report>(`/reports/${encodeURIComponent(id)}`);
  },
  upload(
    reportId: string,
    file: File | File[],
    bundle = false,
  ): Promise<Version> {
    const form = new FormData();
    const files = Array.isArray(file) ? file : [file];
    const fieldName = bundle || files.length > 1 ? "files" : "file";
    for (const selected of files) form.append(fieldName, selected);
    // The browser sets the multipart boundary. The server parses and validates the file.
    return request<Version>(
      `/reports/${encodeURIComponent(reportId)}/versions`,
      {
        method: "POST",
        body: form,
      },
    );
  },
  create(
    name: string,
    period: string,
    file: File | File[],
    bundle = false,
  ): Promise<Report> {
    const form = new FormData();
    form.append("name", name);
    form.append("period", period);
    const files = Array.isArray(file) ? file : [file];
    const fieldName = bundle || files.length > 1 ? "files" : "file";
    for (const selected of files) form.append(fieldName, selected);
    return request<Report>("/reports", { method: "POST", body: form });
  },
  sourceUrl(versionId: string, fileId?: string): string {
    const sourcePath = fileId
      ? `/versions/${encodeURIComponent(versionId)}/files/${encodeURIComponent(fileId)}/source`
      : `/versions/${encodeURIComponent(versionId)}/source`;
    return `${API_BASE}${sourcePath}`;
  },
  apiUrl(path: string): string {
    return `${API_BASE}${path}`;
  },
  async suggestion(issue: Issue, versionId: string): Promise<Suggestion> {
    const result = await request<Suggestion>(
      `/versions/${encodeURIComponent(versionId)}/issues/${encodeURIComponent(issue.id)}/suggestion`,
    );
    // ponytail: dev-only preview of manual evidence until the backend sends excerpts; on by
    // default in `npm run dev`, off with ?evidenceDemo=0, never in production builds. The real
    // response is kept and only labelled sample citations are added.
    if (env?.DEV === true && new URLSearchParams(window.location.search).get("evidenceDemo") !== "0") {
      const { withDemoEvidence } = await import("../dev/evidenceDemo");
      return withDemoEvidence(issue, result);
    }
    return result;
  },
  submit(reportId: string, versionId: string): Promise<void> {
    return request<void>(
      `/reports/${encodeURIComponent(reportId)}/submissions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ versionId }),
      },
    );
  },
};
