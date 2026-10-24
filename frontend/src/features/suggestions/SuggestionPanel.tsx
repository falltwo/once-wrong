import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { reportsApi } from "../../api/reports";
import type { Issue } from "../../types";
import { money } from "../../utils/format";

export function SuggestionPanel({
  issue,
  versionId,
  onClose,
}: {
  issue: Issue;
  versionId: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["suggestion", versionId, issue.id],
    queryFn: () => reportsApi.suggestion(issue),
  });
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
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
          <span className={`status ${issue.repeated ? "bad" : "warning"}`}>
            {issue.repeated ? "重複錯誤" : "待修正"}
          </span>
        </div>
        <h2>{issue.title}</h2>
        <p className="muted">
          資料 {issue.rowId} ·{" "}
          {issue.field === "opening" ? "本月期初" : "險種代碼"}
        </p>
        <div className="comparison">
          <div>
            <span>目前資料</span>
            <strong className="text-red">
              {typeof issue.actual === "number"
                ? money(issue.actual)
                : issue.actual}
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
        <div className="ai-title">
          <Sparkles size={17} />
          <strong>白話說明</strong>
          <span>AI 示範</span>
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
            <p className="explanation">{query.data.explanation}</p>
            {query.data.value !== undefined ? (
              <div className="suggestion">
                <span className="eyebrow">建議修正值</span>
                <strong>{money(query.data.value)}</strong>
                <div className="verified">
                  <ShieldCheck size={15} />
                  示範規則重驗通過
                </div>
                <button
                  className="copy-button"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(
                        String(query.data.value),
                      );
                      setCopied(true);
                      setCopyError(false);
                    } catch {
                      setCopyError(true);
                    }
                  }}
                >
                  {copied ? "已複製修正值" : "複製修正值"}
                </button>
                {copyError && (
                  <small role="alert">
                    無法使用剪貼簿，請手動複製上方數值。
                  </small>
                )}
              </div>
            ) : (
              <div className="neutral-notice">資料不足，沒有可用的修正值。</div>
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
