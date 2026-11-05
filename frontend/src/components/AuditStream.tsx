import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import type { Report, Suggestion, Version } from "../types";
import {
  subscribeAuditSelection,
  selectionStreamResult,
  suggestionStreamLines,
  versionStreamLines,
  type AuditLine,
} from "../utils/auditStream";
import "./audit-stream.css";

type Run = {
  key: string;
  serial: number;
  lines: AuditLine[];
  cursor: number;
  done: boolean;
  summary: string;
};
type Frame = {
  serial: number;
  lines: AuditLine[];
  done: boolean;
  summary: string;
};

export function AuditStream() {
  const client = useQueryClient();
  const [frame, setFrame] = useState<Frame | null>(null);
  const active = useRef<Run | null>(null);

  useEffect(() => {
    let timer: number | null = null;
    let serial = 0;
    const stopTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };
    const pump = () => {
      timer = null;
      const run = active.current;
      if (!run) return;
      if (run.cursor < run.lines.length) {
        run.cursor += 1;
        setFrame({
          serial: run.serial,
          lines: run.lines.slice(0, run.cursor).slice(-6),
          done: false,
          summary: run.done ? "正在呈現收到的操作結果" : run.summary,
        });
        timer = window.setTimeout(pump, 130);
      } else if (run.done) {
        setFrame({
          serial: run.serial,
          lines: run.lines.slice(-6),
          done: true,
          summary: run.summary,
        });
        timer = window.setTimeout(() => {
          if (active.current !== run) return;
          active.current = null;
          setFrame(null);
          timer = null;
        }, 1400);
      }
    };
    const wake = () => {
      stopTimer();
      timer = window.setTimeout(pump, 0);
    };
    const start = (key: string, lines: AuditLine[], summary: string) => {
      const run = active.current;
      if (run?.key === key && !run.done) {
        run.lines.push(...lines);
        run.summary = summary;
      } else {
        active.current = {
          key,
          serial: ++serial,
          lines,
          cursor: 0,
          done: false,
          summary,
        };
      }
      wake();
    };
    const finish = (key: string, lines: AuditLine[], summary: string) => {
      const run = active.current;
      if (!run || run.key !== key) return;
      run.lines.push(...lines);
      run.done = true;
      run.summary = summary;
      wake();
    };
    const queryKey = (versionId: string, issueId: string) => [
      "suggestion",
      versionId,
      issueId,
    ];
    const offSelection = subscribeAuditSelection((selection) => {
      const query = client.getQueryCache().find({
        queryKey: queryKey(selection.versionId, selection.issueId),
        exact: true,
      });
      const key =
        query?.queryHash ??
        JSON.stringify(queryKey(selection.versionId, selection.issueId));
      const safeRule = /^[A-Z][A-Z0-9_-]{0,31}$/.test(selection.ruleId)
        ? selection.ruleId
        : "SELECTED";
      start(
        key,
        [{ text: "ERROR_ROW_SELECTED" }, { text: `RULE: ${safeRule}` }],
        "已選取錯誤，正在開啟說明",
      );
      const result = selectionStreamResult(
        query
          ? {
              status: query.state.status,
              fetchStatus: query.state.fetchStatus,
              data: query.state.data as Suggestion | undefined,
            }
          : undefined,
      );
      if (result) finish(key, result.lines, result.summary);
    });
    const offQuery = client.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || event.query.queryKey[0] !== "suggestion")
        return;
      const key = event.query.queryHash;
      if (event.action.type === "fetch") {
        start(
          key,
          [{ text: "DETAIL_REQUEST" }, { text: "BACKEND_WAIT" }],
          "正在向後端讀取錯誤說明",
        );
      } else if (event.action.type === "success") {
        const review = event.query.state.data as Suggestion;
        finish(
          key,
          suggestionStreamLines(review),
          review.source === "ai" ? "已收到 AI 說明" : "已收到規則固定說明",
        );
      } else if (event.action.type === "error") {
        finish(
          key,
          [
            { text: "DETAIL_REQUEST_FAILED", kind: "error" },
            { text: "RETRY_AVAILABLE", kind: "warning" },
          ],
          "說明讀取失敗，可以重試",
        );
      }
    });
    const offMutation = client.getMutationCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const kind = event.mutation.options.mutationKey?.[0];
      if (kind !== "upload-version" && kind !== "create-report") return;
      const key = `upload:${event.mutation.mutationId}`;
      if (event.action.type === "pending") {
        start(
          key,
          [
            { text: "UPLOAD_REQUEST" },
            { text: "CSV_TRANSFER" },
            { text: "BACKEND_WAIT" },
          ],
          "正在上傳資料並等待檢核結果",
        );
      } else if (event.action.type === "success") {
        const data = event.mutation.state.data;
        const version =
          kind === "create-report"
            ? (data as Report).versions.at(-1)
            : (data as Version);
        finish(
          key,
          version
            ? versionStreamLines(version)
            : [{ text: "RESPONSE_RECEIVED" }],
          "已收到上傳回應",
        );
      } else if (event.action.type === "error") {
        finish(
          key,
          [
            { text: "UPLOAD_REJECTED", kind: "error" },
            { text: "CHECK_DIALOG_MESSAGE", kind: "warning" },
          ],
          "上傳未完成，請查看對話框的錯誤訊息",
        );
      }
    });
    return () => {
      stopTimer();
      active.current = null;
      offSelection();
      offQuery();
      offMutation();
    };
  }, [client]);

  return (
    <section
      className={`sidebar-note audit-panel ${frame ? "is-streaming" : ""}`}
      aria-label="操作事件串流"
    >
      <div className="audit-panel-heading">
        <span className="audit-panel-light" aria-hidden="true" />
        <span>AUDIT STREAM</span>
        <small>操作事件</small>
      </div>
      <div className="audit-panel-body">
        <div className="audit-idle-copy" aria-hidden={Boolean(frame)}>
          <ShieldCheck size={24} aria-hidden="true" />
          <strong>每次修正，都有依據。</strong>
          <p>
            規則把關，AI 說明。
            <br />
            讓下一版更接近正確。
          </p>
        </div>
        {frame && (
          <div className="audit-console" aria-hidden="true">
            <div className="audit-console-label">
              <span>EVENT BUFFER</span>
              <span>{frame.done ? "RECEIVED" : "OBSERVING"}</span>
            </div>
            <div className="audit-code-window">
              <div className="audit-code-lines">
                {frame.lines.map((line, index) => (
                  <div
                    key={`${frame.serial}:${line.text}:${index}`}
                    className={`audit-code-line ${line.kind ?? ""}`}
                  >
                    <span className="audit-code-index">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>{line.text}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="audit-console-footer">
              <span className={frame.done ? "" : "audit-cursor"} />
              {frame.done ? "事件已收到" : "操作狀態視覺化"}
            </div>
          </div>
        )}
      </div>
      <span className="audit-accessible-status" role="status">
        {frame?.summary ?? "等待操作"}
      </span>
    </section>
  );
}
