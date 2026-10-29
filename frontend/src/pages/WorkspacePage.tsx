import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CircleCheck,
  CircleHelp,
  Clock3,
  FileSpreadsheet,
  History,
  LockKeyhole,
  Plus,
  RotateCcw,
  ShieldCheck,
  Search,
  AlertCircle,
} from "lucide-react";
import { reportsApi } from "../api/reports";
import { Dialog } from "../components/Dialog";
import { Loading, ErrorState } from "../components/QueryStates";
import { UploadDialog } from "../features/upload/UploadDialog";
import { SuggestionPanel } from "../features/suggestions/SuggestionPanel";
import { exportReport } from "../utils/exportReport";
import { date, money } from "../utils/format";
import {
  formatCell,
  fileLabel,
  issueAffectsCell,
  issueAffectsRow,
  issueStatus,
  lifeFieldLabels,
  rowLabel,
  rowValues,
  statusClass,
  statusLabel,
} from "../utils/reportData";
import type { Report } from "../types";

export function WorkspacePage() {
  const { reportId = "" } = useParams();
  const query = useQuery({
    queryKey: ["report", reportId],
    queryFn: () => reportsApi.get(reportId),
  });
  if (query.isPending)
    return (
      <main>
        <Loading />
      </main>
    );
  if (query.isError)
    return (
      <main>
        <ErrorState error={query.error} retry={() => query.refetch()} />
      </main>
    );
  return <Workspace report={query.data} />;
}

export function Workspace({ report }: { report: Report }) {
  const [params, setParams] = useSearchParams();
  const [upload, setUpload] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [search, setSearch] = useState("");
  const client = useQueryClient();
  const latest = report.versions.at(-1)!;
  const version =
    report.versions.find((v) => v.id === params.get("version")) ?? latest;
  const filter = params.get("filter") ?? "all";
  const fileScope = params.get("file") ?? "all";
  const files = version.files ?? [];
  const selected = params.has("issue")
    ? version.issues.find((i) => i.id === params.get("issue"))
    : version.issues[0];
  const repeated = version.issues.filter(
    (i) => issueStatus(i) === "repeated",
  ).length;
  const regressed = version.issues.filter(
    (i) => issueStatus(i) === "regressed",
  ).length;
  const notEvaluated = version.summary?.notEvaluatedChecks ?? 0;
  const submitted = report.submittedVersionId === version.id;
  const completed = version.validationStatus === "completed";
  const canSubmit =
    report.canSubmit === true &&
    completed &&
    version.id === latest.id &&
    !submitted &&
    version.issues.length === 0 &&
    notEvaluated === 0;
  const updateParams = (values: Record<string, string>) =>
    setParams((old) => {
      const next = new URLSearchParams(old);
      for (const [key, value] of Object.entries(values)) next.set(key, value);
      return next;
    });
  const submit = useMutation({
    mutationFn: () => reportsApi.submit(report.id, version.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["report", report.id] });
      setConfirm(false);
    },
  });
  const scopedRows = version.rows.filter((row) => {
    if (fileScope === "all" || !files.length) return true;
    const file = files.find((candidate) =>
      row.id.startsWith(`${candidate.id}:`),
    );
    return (
      ("fileId" in row ? row.fileId : undefined) === fileScope ||
      file?.id === fileScope
    );
  });
  const visibleRows = scopedRows.filter((row) => {
    const issues = version.issues.filter((issue) =>
      issueAffectsRow(issue, row),
    );
    const searchable = `${row.id} ${"row" in row ? row.row : ""} ${Object.values(rowValues(row)).join(" ")}`;
    return (
      (filter === "all" ||
        (filter === "errors" && issues.length) ||
        (filter === "repeated" &&
          issues.some((i) => issueStatus(i) === "repeated")) ||
        (filter === "regressed" &&
          issues.some((i) => issueStatus(i) === "regressed"))) &&
      searchable.toLowerCase().includes(search.toLowerCase())
    );
  });
  const columns =
    fileScope !== "all" && files.length
      ? (files.find((file) => file.id === fileScope)?.columns ??
        version.columns ??
        [])
      : files.length
        ? [...new Set(files.flatMap((file) => file.columns))]
        : (version.columns ?? ["product", "previous", "opening"]);
  const isLifeProfile = version.schemaProfileId === "life_underwriting_v1";
  return (
    <main className="workspace">
      <Link className="back-link" to="/reports">
        <ArrowLeft size={14} />
        所有報表
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            REPORT VALIDATION <span>／ {report.period}</span>
          </div>
          <h1>
            {report.period.split("-")[0]} 年{" "}
            {Number(report.period.split("-")[1])} 月{report.name}
            <span className="version-chip">第 {version.number} 版</span>
          </h1>
          <p>在每次送出之前，讓資料多一份確定。</p>
        </div>
        <button className="primary" onClick={() => setUpload(true)}>
          <Plus size={17} />
          上傳修正版
        </button>
      </div>
      <div className="workflow">
        <span className="complete">
          <Check size={14} />
          上傳報表
        </span>
        <div />
        <span className="current">
          <Search size={14} />
          檢核與修正
        </span>
        <div />
        <span className={submitted ? "complete" : ""}>
          <ShieldCheck size={14} />
          確認送出
        </span>
        <small>
          <Clock3 size={13} />
          最後更新 {date(version.createdAt)}
        </small>
      </div>
      <section className="metrics" aria-label="檢核摘要">
        <div>
          <span>報表資料</span>
          <strong>
            {version.rows.length}
            <small>筆</small>
          </strong>
          <p>本次檢核涵蓋的資料</p>
        </div>
        <div>
          <span>通過檢核</span>
          <strong className="text-green">
            {version.summary?.passedChecks ?? "—"}
            <small>項</small>
          </strong>
          <p>共執行 {version.summary?.totalChecks ?? "—"} 項規則檢查</p>
        </div>
        <div>
          <span>待修正</span>
          <strong className="text-red">
            {version.summary?.failedChecks ?? "—"}
            <small>項</small>
          </strong>
          <p>需要核對與調整</p>
        </div>
        <div>
          <span>其中重複錯誤</span>
          <strong className="text-orange">
            {repeated}
            <small>項</small>
          </strong>
          <p>與前一版相同的問題</p>
        </div>
      </section>
      <div
        className={`notice ${!completed || version.issues.length || notEvaluated ? "blocked" : "passed"}`}
        role="status"
      >
        {!completed || version.issues.length || notEvaluated ? (
          <LockKeyhole size={20} />
        ) : (
          <CircleCheck size={20} />
        )}
        <div>
          <strong>
            {submitted
              ? "已完成內部確認"
              : version.id !== latest.id
                ? "正在檢視歷史版本"
                : !completed
                  ? "檢核結果尚未就緒"
                  : notEvaluated
                    ? "部分檢核未執行，不能視為全數通過"
                    : version.issues.length
                      ? "送出已鎖定，請先完成修正"
                      : "所有示範檢核已通過"}
          </strong>
          <p>
            {version.id !== latest.id
              ? "請切換到最新版本進行送出確認。"
              : submitted
                ? "確認紀錄已保存在後端，未送往外部申報系統。"
                : !completed
                  ? "請等待後端完成檢核；目前不能確認送出。"
                  : notEvaluated
                    ? `有 ${notEvaluated} 項檢核未執行：${version.evidence?.notEvaluated?.map((item) => item.reason).join("；") || "請依後端檢核說明補齊資料或格式"}。`
                    : repeated
                      ? `有 ${repeated} 項錯誤在前後兩版都未通過，請依檢核說明核對來源資料。`
                      : regressed
                        ? `有 ${regressed} 項錯誤在修正後再次出現，請重新核對來源資料。`
                        : version.issues.length
                          ? "修改資料並重新上傳，系統會再次檢查。"
                          : "請完成最後人工確認，再記錄內部確認狀態。"}
          </p>
        </div>
        <ShieldCheck className="notice-decoration" size={30} />
      </div>
      <div className="section-line results-heading">
        <h2>
          <FileSpreadsheet size={18} />
          資料檢核結果
        </h2>
        <div className="toolbar">
          <label className="version-select">
            <History size={15} />
            <select
              aria-label="選擇報表版本"
              value={version.id}
              onChange={(e) =>
                updateParams({
                  version: e.target.value,
                  issue: "",
                  file: "all",
                })
              }
            >
              {[...report.versions].reverse().map((v) => (
                <option key={v.id} value={v.id}>
                  第 {v.number} 版{v.id === latest.id ? "（最新）" : ""}
                </option>
              ))}
            </select>
          </label>
          {files.length > 0 && (
            <label className="version-select">
              <FileSpreadsheet size={15} />
              <select
                aria-label="選擇檔案"
                value={fileScope}
                onChange={(event) => updateParams({ file: event.target.value })}
              >
                <option value="all">全部檔案</option>
                {files.map((file) => (
                  <option key={file.id} value={file.id}>
                    {fileLabel(file)} · {file.filename}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(fileScope !== "all" || files.length === 0) && (
            <a
              className="secondary compact source-download"
              href={reportsApi.sourceUrl(
                version.id,
                fileScope === "all" ? undefined : fileScope,
              )}
              download
            >
              <ArrowDownToLine size={15} />
              下載來源檔
            </a>
          )}
          <button
            className="secondary compact"
            onClick={() => exportReport(report, version)}
          >
            <ArrowDownToLine size={15} />
            下載報告
          </button>
        </div>
      </div>
      <section className={`results ${selected ? "" : "no-detail"}`}>
        <div className="table-panel">
          <div className="table-tools">
            <div className="tabs" role="group" aria-label="篩選檢核結果">
              {[
                ["all", "全部資料"],
                ["errors", "僅看錯誤"],
                ["repeated", "重複錯誤"],
                ["regressed", "修正後復發"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={filter === value}
                  className={filter === value ? "selected" : ""}
                  onClick={() => updateParams({ filter: value })}
                >
                  {label}
                  {value === "errors" && <span>{version.issues.length}</span>}
                  {value === "repeated" && <span>{repeated}</span>}
                  {value === "regressed" && <span>{regressed}</span>}
                </button>
              ))}
            </div>
            <label className="search-box">
              <Search size={15} />
              <input
                aria-label="搜尋資料"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜尋資料列或欄位內容"
              />
            </label>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{isLifeProfile ? "資料列" : "資料 ID"}</th>
                  {columns.map((column) => (
                    <th key={column}>
                      {lifeFieldLabels[column] ??
                        {
                          product: "險種",
                          previous: "上月期末",
                          opening: "本月期初",
                        }[column] ??
                        column}
                    </th>
                  ))}
                  <th>檢核狀態</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const issues = version.issues.filter((issue) =>
                    issueAffectsRow(issue, row),
                  );
                  const values = rowValues(row);
                  const issue = issues[0];
                  return (
                    <tr
                      key={row.id}
                      className={
                        selected && issueAffectsRow(selected, row)
                          ? "selected-row"
                          : ""
                      }
                    >
                      <td className="row-id">{rowLabel(row)}</td>
                      {columns.map((column) => {
                        const value = values[column] ?? null;
                        const invalid = issues.some((currentIssue) =>
                          issueAffectsCell(currentIssue, row, column),
                        );
                        const isAmount =
                          !isLifeProfile &&
                          (column === "previous" || column === "opening") &&
                          typeof value === "number";
                        return (
                          <td
                            key={column}
                            className={`${isAmount ? "number" : ""} ${invalid ? "invalid-cell" : ""}`}
                          >
                            {isAmount
                              ? money(value as number)
                              : formatCell(value)}
                          </td>
                        );
                      })}
                      <td>
                        {issue ? (
                          <div className="row-issues">
                            {issues.map((i) => (
                              <button
                                key={i.id}
                                className={`status issue-button ${statusClass(issueStatus(i))}`}
                                onClick={() => updateParams({ issue: i.id })}
                                aria-label={`查看 ${row.id} ${i.ruleId} 錯誤`}
                              >
                                {issueStatus(i) !== "new" ? (
                                  <RotateCcw size={12} />
                                ) : (
                                  <AlertCircle size={12} />
                                )}
                                {statusLabel(issueStatus(i))}
                                {issues.length > 1 && ` ${i.ruleId}`}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span className="status good">
                            <Check size={13} />
                            通過
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!visibleRows.length && (
              <div className="table-empty">
                <CircleCheck size={24} />
                <p>沒有符合條件的資料</p>
                <button
                  className="text-button"
                  onClick={() => {
                    setSearch("");
                    updateParams({ filter: "all" });
                  }}
                >
                  顯示全部資料
                </button>
              </div>
            )}
          </div>
          <div className="table-footer">
            <span>
              顯示 {visibleRows.length} / {scopedRows.length} 筆資料
            </span>
            <span>金額單位：新臺幣元</span>
          </div>
          <div className="table-hint">
            <CircleHelp size={15} />
            點選錯誤標籤，查看規則與修正建議。
          </div>
        </div>
        {selected && (
          <SuggestionPanel
            key={`${version.id}:${selected.id}`}
            issue={selected}
            versionId={version.id}
            report={report}
            onClose={() => updateParams({ issue: "" })}
          />
        )}
      </section>
      <div className="workspace-bottom">
        <div>
          <ShieldCheck size={18} />
          <span>每個版本與檢核結果，都有紀錄可查。</span>
          <Link to={`/reports/${report.id}/report?version=${version.id}`}>
            查看紀錄
            <ArrowRight size={13} />
          </Link>
        </div>
        <button
          className="primary"
          disabled={!canSubmit}
          onClick={() => {
            submit.reset();
            setConfirm(true);
          }}
        >
          {canSubmit ? <ShieldCheck size={16} /> : <LockKeyhole size={16} />}
          {submitted ? "已內部確認" : "確認送出（內部紀錄）"}
        </button>
      </div>
      {upload && (
        <UploadDialog
          report={report}
          onClose={() => setUpload(false)}
          onUploaded={(id) => {
            updateParams({ version: id, issue: "", filter: "all" });
            setUpload(false);
          }}
        />
      )}
      {confirm && (
        <Dialog
          title="確認內部送出紀錄"
          onClose={() => setConfirm(false)}
          busy={submit.isPending}
        >
          <p>
            第 {version.number}{" "}
            版已通過示範規則。請確認您已核對來源資料與報表內容。
          </p>
          <p className="muted">
            此操作將確認紀錄保存在後端，不會送往任何外部申報系統。
          </p>
          {submit.isError && (
            <p className="error-message" role="alert">
              {submit.error.message}
            </p>
          )}
          <div className="dialog-actions">
            <button
              className="secondary"
              disabled={submit.isPending}
              onClick={() => setConfirm(false)}
            >
              返回檢查
            </button>
            <button
              className="primary"
              disabled={submit.isPending}
              onClick={() => submit.mutate()}
            >
              {submit.isPending ? "確認中…" : "已核對，記錄確認"}
            </button>
          </div>
        </Dialog>
      )}
    </main>
  );
}
