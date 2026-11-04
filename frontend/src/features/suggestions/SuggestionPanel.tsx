import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { reportsApi } from "../../api/reports";
import type { Citation, Issue, Report } from "../../types";
import { ManualEvidenceList, ManualEvidenceView, Seal } from "./ManualEvidence";
import {
  formatCell,
  datasetLabels,
  fixedInVersion,
  issueFacts,
  issueLocation,
  lifeFieldLabels,
  issueStatus,
  statusClass,
  statusLabel,
} from "../../utils/reportData";

const fieldNames: Record<string, string> = {
  ...lifeFieldLabels,
  id: "資料 ID",
  product: "險種代碼",
  previous: "上月期末",
  opening: "本月期初",
};

const formatValue = formatCell;

const sourceLabels = {
  ai: "AI 審核",
  fallback_llm_error: "固定說明 · AI 暫不可用",
  fallback_number_guard: "固定說明 · 數字檢查未通過",
} as const;

export function SuggestionPanel({
  issue,
  versionId,
  report,
  onClose,
}: {
  issue: Issue;
  versionId: string;
  report: Report;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["suggestion", versionId, issue.id],
    queryFn: () => reportsApi.suggestion(issue, versionId),
  });
  const verifiedSuggestion =
    query.data?.verification === "passed" &&
    query.data.suggestion?.verification === "passed"
      ? query.data.suggestion
      : undefined;
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [evidence, setEvidence] = useState<Citation | null>(null);
  const closeEvidence = useCallback(() => setEvidence(null), []);
  const versionNumber = report.versions.find((v) => v.id === versionId)?.number ?? 0;
  const fixedIn = fixedInVersion(issue, versionNumber, report.versions);
  return (
    <aside className="detail-panel">
      <div className="panel-title">
        <span>
          <Search size={17} />
          錯誤詳情
        </span>
        <button
          className="icon-button"
          aria-label="關閉錯誤詳情"
          onClick={onClose}
        >
          <X size={17} />
        </button>
      </div>
      <div className="panel-pages" data-page={evidence ? "evidence" : "main"}>
      <div className="panel-body panel-page" inert={evidence !== null}>
        {fixedIn ? <Seal fixedIn={fixedIn} /> : null}
        <div className="issue-tags">
          <span className="rule-tag">{issue.ruleId}</span>
          <span className={`status ${statusClass(issueStatus(issue))}`}>
            {statusLabel(issueStatus(issue))}
          </span>
        </div>
        <h2>{issue.title}</h2>
        <p className="muted">
          {issueLocation(issue)} · {issue.ruleId}
        </p>
        {(issue.firstSeenNumber ||
          issue.prevSeenNumber ||
          issue.fixedInNumber) && (
          <div className="issue-history" aria-label="錯誤版本歷程">
            {issue.firstSeenNumber && (
              <span>
                首次出現：
                <Link
                  to={`/reports/${report.id}?version=${report.versions.find((v) => v.number === issue.firstSeenNumber)?.id ?? versionId}`}
                >
                  第 {issue.firstSeenNumber} 版
                </Link>
              </span>
            )}
            {issue.prevSeenNumber && (
              <span>
                上次出現：
                <Link
                  to={`/reports/${report.id}?version=${report.versions.find((v) => v.number === issue.prevSeenNumber)?.id ?? versionId}`}
                >
                  第 {issue.prevSeenNumber} 版
                </Link>
              </span>
            )}
            {issue.fixedInNumber && (
              <span>
                曾修正：
                <Link
                  to={`/reports/${report.id}?version=${report.versions.find((v) => v.number === issue.fixedInNumber)?.id ?? versionId}`}
                >
                  第 {issue.fixedInNumber} 版
                </Link>
              </span>
            )}
          </div>
        )}
        <div className="comparison">
          {issueFacts(issue).map(([field, value]) => (
            <div key={field}>
              <span>{fieldNames[field] ?? field}</span>
              <strong className="text-red">{formatValue(value)}</strong>
            </div>
          ))}
          {issue.expected !== undefined && (
            <div>
              <span>規則預期值</span>
              <strong>{formatValue(issue.expected)}</strong>
            </div>
          )}
          {!issueFacts(issue).length && issue.expected === undefined && (
            <div>
              <span>修正方式</span>
              <strong>核對來源資料</strong>
            </div>
          )}
        </div>
        <div className="ai-title">
          <Sparkles size={17} />
          <strong>白話說明</strong>
          {query.data && (
            <span>
              {sourceLabels[query.data.source]} · {query.data.model}
            </span>
          )}
        </div>
        {query.isPending ? (
          <p className="muted" role="status">
            正在載入說明…
          </p>
        ) : query.isError ? (
          <div>
            <p>說明暫時無法載入，仍可依規則修正。</p>
            <button onClick={() => query.refetch()}>重試</button>
          </div>
        ) : (
          <>
            <h3 className="suggestion-title">{query.data.title}</h3>
            <p className="explanation">{query.data.explanation}</p>
            {verifiedSuggestion ? (
              <div className="suggestion">
                <span className="eyebrow">建議修正</span>
                <ul className="suggestion-changes">
                  {verifiedSuggestion.changes.map((change) => (
                    <li
                      key={`${change.fileId ?? ""}:${change.rowId}:${change.column}`}
                    >
                      <span>
                        {change.datasetType
                          ? `${datasetLabels[change.datasetType] ?? change.datasetType} · `
                          : ""}
                        {change.rowId} ·{" "}
                        {fieldNames[change.column] ?? change.column}
                      </span>
                      <strong>{formatValue(change.value)}</strong>
                    </li>
                  ))}
                </ul>
                <p>{verifiedSuggestion.reason}</p>
                <div className="verified">
                  <ShieldCheck size={15} />
                  修法已通過規則重驗
                </div>
                <button
                  className="copy-button"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(
                        verifiedSuggestion.changes
                          .map(
                            (change) =>
                              `${change.rowId} ${fieldNames[change.column] ?? change.column}: ${formatValue(change.value)}`,
                          )
                          .join("\n"),
                      );
                      setCopied(true);
                      setCopyError(false);
                    } catch {
                      setCopyError(true);
                    }
                  }}
                >
                  {copied ? "已複製修正建議" : "複製修正建議"}
                </button>
                {copyError && (
                  <small role="alert">
                    無法使用剪貼簿，請手動複製上方修正建議。
                  </small>
                )}
              </div>
            ) : (
              <div className="neutral-notice">
                目前沒有通過規則重驗的修法，請核對來源資料後自行修改。
              </div>
            )}
            {query.data.rejectedSuggestions.length > 0 && (
              <div className="rejected-suggestions">
                <strong>
                  有 {query.data.rejectedSuggestions.length} 個修法未通過重驗
                </strong>
                <ul>
                  {query.data.rejectedSuggestions.map((reason, index) => (
                    <li key={`${index}:${reason}`}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}
            {query.data.blockedNumbers.length > 0 && (
              <p className="blocked-numbers" role="status">
                說明中有無法由資料或手冊佐證的數字，已改用固定說明。
              </p>
            )}
            {query.data.citations.length > 0 && (
              <ManualEvidenceList
                citations={query.data.citations}
                rejectedQuotes={query.data.rejectedQuotes?.length ?? 0}
                onOpen={setEvidence}
              />
            )}
          </>
        )}
        <p className="panel-footnote">
          請核對來源後自行修改檔案，再上傳修正版。系統不會自動更動原始資料。
        </p>
      </div>
      <div className="panel-body panel-page" inert={evidence === null}>
        {evidence && (
          <ManualEvidenceView citation={evidence} fixedIn={fixedIn} onBack={closeEvidence} />
        )}
      </div>
      </div>
    </aside>
  );
}
