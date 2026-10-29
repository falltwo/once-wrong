import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { Link } from "react-router-dom";
import { reportsApi } from "../../api/reports";
import type { Issue, Version, VersionFile } from "../../types";
import { money } from "../../utils/format";
import { repeatState, stateLabel } from "../../utils/issues";

const fieldNames: Record<string, string> = {
  id: "資料 ID",
  product: "險種代碼",
  previous: "上月期末",
  opening: "本月期初",
};

const formatValue = (value: string | number | null) => {
  if (value === null || value === "") return "（空白）";
  if (typeof value === "number") return money(value);
  return value;
};

const sourceLabels = {
  ai: "AI 審核",
  fallback_llm_error: "固定說明 · AI 暫不可用",
  fallback_number_guard: "固定說明 · 數字檢查未通過",
} as const;

export function SuggestionPanel({
  issue,
  versionId,
  files,
  reportId,
  versions,
  onClose,
}: {
  issue: Issue;
  versionId: string;
  files?: VersionFile[];
  reportId: string;
  versions: Version[];
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
  const versionLink = (number: number, label: string) => {
    const version = versions.find((item) => item.number === number);
    return version ? (
      <Link
        to={`/reports/${reportId}?version=${encodeURIComponent(version.id)}`}
      >
        {label}
      </Link>
    ) : (
      label
    );
  };
  const fileLabel = (id?: string) =>
    files?.find((file) => file.id === id)?.filename ?? id;
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
      <div className="panel-body">
        <div className="issue-tags">
          <span className="rule-tag">{issue.ruleId}</span>
          <span
            className={`status ${repeatState(issue) === "new" ? "warning" : "bad"}`}
          >
            {stateLabel(issue)}
          </span>
        </div>
        <h2>{issue.title}</h2>
        {(issue.firstSeenNumber || issue.prevSeenNumber) && (
          <p className="issue-history">
            {issue.firstSeenNumber ? (
              <>
                首次出現：
                {versionLink(
                  issue.firstSeenNumber,
                  `第 ${issue.firstSeenNumber} 版`,
                )}
                <br />
              </>
            ) : null}
            {issue.prevSeenNumber ? (
              <>
                前次出現：
                {versionLink(
                  issue.prevSeenNumber,
                  `第 ${issue.prevSeenNumber} 版`,
                )}
                <br />
              </>
            ) : null}
            {repeatState(issue) === "regressed" && issue.prevSeenNumber ? (
              <>
                曾修好：
                {versionLink(
                  issue.prevSeenNumber + 1,
                  `第 ${issue.prevSeenNumber + 1} 版`,
                )}
                ；本版再次出現。
              </>
            ) : null}
          </p>
        )}
        {issue.cells?.length ? (
          <section className="issue-cells" aria-label="出錯格子">
            {issue.cells.map((cell) => (
              <div key={`${cell.fileId ?? ""}:${cell.row}:${cell.column}`}>
                <small>
                  {fileLabel(cell.fileId) ? `${fileLabel(cell.fileId)} · ` : ""}
                  第 {cell.row} 列 · {cell.column}
                </small>
                <strong>{formatValue(cell.value)}</strong>
              </div>
            ))}
          </section>
        ) : (
          <>
            <p className="muted">
              資料 {issue.rowId} ·{" "}
              {issue.field
                ? (fieldNames[issue.field] ?? issue.field)
                : "請核對檢核說明"}
            </p>
            <div className="comparison">
              <div>
                <span>目前資料</span>
                <strong className="text-red">
                  {typeof issue.actual === "number"
                    ? money(issue.actual)
                    : (issue.actual ?? "請核對來源")}
                </strong>
              </div>
              <div>
                <span>
                  {issue.expected !== undefined ? "規則預期值" : "修正方式"}
                </span>
                <strong>
                  {issue.expected !== undefined
                    ? money(issue.expected)
                    : "核對來源資料"}
                </strong>
              </div>
            </div>
          </>
        )}
        {issue.facts && Object.keys(issue.facts).length > 0 && (
          <details className="issue-facts">
            <summary>規則依據與已知值</summary>
            <dl>
              {Object.entries(issue.facts).map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{formatValue(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
        {!!issue.contextRowIds?.length && (
          <p className="muted">
            參考資料列：{issue.contextRowIds.join("、")}（僅供核對）
          </p>
        )}
        <div className="ai-title">
          <Sparkles size={17} />
          <strong>白話說明</strong>
          {query.data && <span>{sourceLabels[query.data.source]}</span>}
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
            <p className="model-source">審核模型：{query.data.model}</p>
            <p className="explanation">{query.data.explanation}</p>
            {verifiedSuggestion ? (
              <div className="suggestion">
                <span className="eyebrow">建議修正</span>
                <ul className="suggestion-changes">
                  {verifiedSuggestion.changes.map((change) => (
                    <li
                      key={`${change.fileId ?? ""}:${change.row}:${change.column}`}
                    >
                      <span>
                        {fileLabel(change.fileId)
                          ? `${fileLabel(change.fileId)} · `
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
                              `${fileLabel(change.fileId) ?? ""} ${change.rowId} ${fieldNames[change.column] ?? change.column}: ${formatValue(change.value)}`,
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
            {query.data.source !== "ai" && (
              <button
                className="secondary"
                disabled={query.isFetching}
                onClick={() => query.refetch()}
              >
                {query.isFetching ? "重新取得中…" : "重試 AI 說明"}
              </button>
            )}
            {query.data.citations.length > 0 && (
              <section className="suggestion-citations" aria-label="手冊依據">
                <strong>手冊依據</strong>
                <ul>
                  {query.data.citations.map((citation) => (
                    <li key={citation.id}>
                      <span>{citation.source}</span>
                      {citation.section.length > 0 && (
                        <small>{citation.section.join(" › ")}</small>
                      )}
                      {citation.page !== null &&
                        citation.page !== undefined && (
                          <small>
                            第 {citation.page} 頁 · {citation.id}
                          </small>
                        )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
        <p className="panel-footnote">
          請核對來源後自行修改檔案，再上傳修正版。系統不會自動更動原始資料。
        </p>
      </div>
    </aside>
  );
}
