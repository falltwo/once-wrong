import type { Suggestion, Version } from "../types";

export type AuditLine = {
  text: string;
  kind?: "good" | "warning" | "error" | "demo";
};
export type AuditSelection = {
  versionId: string;
  issueId: string;
  ruleId: string;
};
const selections = new Set<(selection: AuditSelection) => void>();

/** Ephemeral UI events only: no storage, network, raw rows, filenames or policy IDs. */
export function announceAuditSelection(selection: AuditSelection) {
  selections.forEach((listener) => listener(selection));
}
export function subscribeAuditSelection(
  listener: (selection: AuditSelection) => void,
) {
  selections.add(listener);
  return () => {
    selections.delete(listener);
  };
}

/** Re-selecting the current row does not itself retry a failed query. */
export function selectionStreamResult(state?: {
  status: string;
  fetchStatus: string;
  data?: Suggestion;
}): { lines: AuditLine[]; summary: string } | null {
  if (!state || state.fetchStatus === "fetching") return null;
  if (state.status === "error") {
    return {
      lines: [
        { text: "DETAIL_REQUEST_FAILED", kind: "error" },
        { text: "RETRY_AVAILABLE", kind: "warning" },
      ],
      summary: "上次說明讀取失敗，請按說明區的重試",
    };
  }
  if (!state.data) return null;
  return {
    lines: [
      { text: "CACHE_HIT", kind: "good" },
      ...suggestionStreamLines(state.data),
    ],
    summary: "已讀取快取說明",
  };
}

export function suggestionStreamLines(review: Suggestion): AuditLine[] {
  const lines: AuditLine[] = [{ text: "RESPONSE_RECEIVED", kind: "good" }];
  if (review.source === "ai") {
    lines.push({ text: "AI_READY", kind: "good" });
  } else {
    lines.push({
      text:
        review.source === "fallback_number_guard"
          ? "NUMBER_GUARD: FALLBACK"
          : "AI_UNAVAILABLE: FALLBACK",
      kind: "warning",
    });
    lines.push({ text: "RULE_TEXT_READY", kind: "good" });
  }
  for (const citation of review.citations.slice(0, 3)) {
    if (!citation.page || !Number.isFinite(citation.page)) continue;
    const demo = citation.id.startsWith("LIFE-RULE-DEMO");
    lines.push({
      text: `${demo ? "DEMO_CITATION" : "CITATION"}: p.${citation.page}`,
      kind: demo ? "demo" : "good",
    });
  }
  if (
    review.verification === "passed" &&
    review.suggestion?.verification === "passed"
  ) {
    const demo = review.suggestion.reason.includes("示範資料");
    lines.push({
      text: demo ? "DEMO_FIX: PREVIEW" : "FIX_RECHECK: PASS",
      kind: demo ? "demo" : "good",
    });
  }
  return lines;
}

export function versionStreamLines(version: Version): AuditLine[] {
  const lines: AuditLine[] = [
    { text: "UPLOAD_ACCEPTED", kind: "good" },
    { text: `VERSION_SAVED: V${version.number}`, kind: "good" },
  ];
  if (version.validationStatus !== "completed" || !version.summary) {
    return [...lines, { text: "CHECK_RESULT: PENDING", kind: "warning" }];
  }
  const summary = version.summary;
  lines.push(
    { text: `ROWS_RECEIVED: ${version.rows.length}` },
    { text: `CHECKS_PASSED: ${summary.passedChecks}`, kind: "good" },
    {
      text: `CHECKS_FAILED: ${summary.failedChecks}`,
      kind: summary.failedChecks ? "warning" : "good",
    },
  );
  if (summary.notEvaluatedChecks) {
    lines.push({
      text: `CHECKS_UNEVALUATED: ${summary.notEvaluatedChecks}`,
      kind: "warning",
    });
  }
  return lines;
}
