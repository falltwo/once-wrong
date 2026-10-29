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
import type { Report } from "../types";
import {
  fieldLabel,
  isTextRow,
  issueTouchesRow,
  repeatState,
  rowValues,
  stateLabel,
} from "../utils/issues";

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
  const selected = params.has("issue")
    ? version.issues.find((i) => i.id === params.get("issue"))
    : version.issues[0];
  const repeated = version.issues.filter((i) => i.repeated).length;
  const regressed = version.issues.filter(
    (i) => repeatState(i) === "regressed",
  ).length;
  const activeFile = version.files?.find(
    (file) => file.id === params.get("file"),
  );
  const columns =
    activeFile?.columns ??
    version.columns ??
    (version.rows[0] && isTextRow(version.rows[0])
      ? Object.keys(version.rows[0].values)
      : ["product", "previous", "opening"]);
  const notEvaluated = version.summary?.notEvaluatedChecks ?? 0;
  const blockingIssues = version.issues.filter(
    (issue) => issue.severity !== "warning",
  ).length;
  const blocked =
    version.validationStatus !== "completed" ||
    blockingIssues > 0 ||
    notEvaluated > 0;
  const submitted = report.submittedVersionId === version.id;
  const completed = version.validationStatus === "completed";
  const canSubmit =
    report.canSubmit === true &&
    completed &&
    version.id === latest.id &&
    !submitted;
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
  const visibleRows = version.rows.filter((row) => {
    const issues = version.issues.filter((i) => issueTouchesRow(i, row));
    return (
      (!activeFile || (isTextRow(row) && row.fileId === activeFile.id)) &&
      (filter === "all" ||
        (filter === "errors" && issues.length) ||
        issues.some((i) => repeatState(i) === filter)) &&
      `${row.id} ${Object.values(rowValues(row)).join(" ")}`
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  });
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
          <p>
            {notEvaluated
              ? `目前列出 ${version.summary?.totalChecks ?? "—"} 項檢查，含 ${notEvaluated} 項未評估`
              : `共執行 ${version.summary?.totalChecks ?? "—"} 項規則檢查`}
          </p>
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
          <span>連續／復發錯誤</span>
          <strong className="text-orange">
            {repeated}／{regressed}
            <small>項</small>
          </strong>
          <p>上一版仍錯／曾修好後再次出現</p>
        </div>
      </section>
      <div className={`notice ${blocked ? "blocked" : "passed"}`} role="status">
        {blocked ? <LockKeyhole size={20} /> : <CircleCheck size={20} />}
        <div>
          <strong>
            {submitted
              ? "已完成內部確認"
              : version.id !== latest.id
                ? "正在檢視歷史版本"
                : !completed
                  ? "檢核結果尚未就緒"
                  : notEvaluated
                    ? "仍有檢查未評估，暫不能確認"
                    : blockingIssues
                      ? "送出已鎖定，請先完成修正"
                      : "目前適用檢核已通過"}
          </strong>
          <p>
            {version.id !== latest.id
              ? "請切換到最新版本進行送出確認。"
              : submitted
                ? "確認紀錄已保存在後端，未送往外部申報系統。"
                : !completed
                  ? "請等待後端完成檢核；目前不能確認送出。"
                  : notEvaluated
                    ? `有 ${notEvaluated} 項檢查未評估，請查看缺少的檔案或尚未支援的檢核。`
                    : regressed
                      ? `有 ${regressed} 項曾經修好的錯誤再次出現，請查看各項的歷史版本。`
                      : repeated
                        ? `有 ${repeated} 項錯誤在前後兩版都未通過，請依檢核說明核對來源資料。`
                        : blockingIssues
                          ? "修改資料並重新上傳，系統會再次檢查。"
                          : version.issues.length
                            ? "仍有提醒事項，請核對後完成最後人工確認。"
                            : "請完成最後人工確認，再記錄內部確認狀態。"}
          </p>
          {notEvaluated > 0 && version.evidence?.notEvaluated && (
            <details>
              <summary>查看未評估原因</summary>
              <ul>
                {version.evidence.notEvaluated.map((item) => (
                  <li key={item.code}>{item.reason}</li>
                ))}
              </ul>
              {version.evidence.notice && <p>{version.evidence.notice}</p>}
            </details>
          )}
        </div>
        <ShieldCheck className="notice-decoration" size={30} />
      </div>
      {version.files && (
        <section className="version-files" aria-label="本版本檔案">
          <label>
            檔案範圍
            <select
              aria-label="選擇檔案"
              value={activeFile?.id ?? ""}
              onChange={(event) => updateParams({ file: event.target.value })}
            >
              <option value="">全部檔案</option>
              {version.files.map((file) => (
                <option key={file.id} value={file.id}>
                  {file.datasetType} · {file.filename}
                </option>
              ))}
            </select>
          </label>
          <div>
            {version.files.map((file) => (
              <a
                key={file.id}
                href={reportsApi.sourceUrl(version.id, file.id)}
                download
              >
                <ArrowDownToLine size={14} />
                {file.filename}
              </a>
            ))}
          </div>
        </section>
      )}
      {version.issues.some(
        (issue) => !version.rows.some((row) => issueTouchesRow(issue, row)),
      ) && (
        <section className="unlocated-issues" aria-label="檔案與整體檢核事項">
          <h2>檔案與整體檢核事項</h2>
          {version.issues
            .filter(
              (issue) =>
                !version.rows.some((row) => issueTouchesRow(issue, row)),
            )
            .map((issue) => (
              <button
                key={issue.id}
                className="secondary"
                onClick={() => updateParams({ issue: issue.id })}
              >
                {issue.ruleId} · {issue.title}
              </button>
            ))}
        </section>
      )}
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
                updateParams({ version: e.target.value, issue: "" })
              }
            >
              {[...report.versions].reverse().map((v) => (
                <option key={v.id} value={v.id}>
                  第 {v.number} 版{v.id === latest.id ? "（最新）" : ""}
                </option>
              ))}
            </select>
          </label>
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
                ["new", "新錯誤"],
                ["repeated", "重複錯誤"],
                ["regressed", "修好後復發"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={filter === value}
                  className={filter === value ? "selected" : ""}
                  onClick={() => updateParams({ filter: value, issue: "" })}
                >
                  {label}
                  {value === "errors" && <span>{version.issues.length}</span>}
                </button>
              ))}
            </div>
            <label className="search-box">
              <Search size={15} />
              <input
                aria-label="搜尋資料"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜尋代碼或 ID"
              />
            </label>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>資料 ID</th>
                  {columns.map((column) => (
                    <th key={column}>{fieldLabel(column)}</th>
                  ))}
                  <th>檢核狀態</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const issues = version.issues.filter((i) =>
                    issueTouchesRow(i, row),
                  );
                  const issue = issues[0];
                  return (
                    <tr
                      key={row.id}
                      className={
                        selected && issueTouchesRow(selected, row)
                          ? "selected-row"
                          : ""
                      }
                    >
                      <td className="row-id">
                        {isTextRow(row)
                          ? `${row.datasetType ? `${row.datasetType} · ` : ""}第 ${row.row} 列`
                          : row.id}
                      </td>
                      {columns.map((column) => {
                        const value = rowValues(row)[column];
                        const invalid = issues.some(
                          (item) =>
                            item.field === column ||
                            item.cells?.some(
                              (cell) =>
                                cell.column === column && cell.rowId === row.id,
                            ),
                        );
                        return (
                          <td
                            key={column}
                            className={`${invalid ? "invalid-cell" : ""} ${typeof value === "number" ? "number" : ""}`}
                          >
                            <span className="cell-value">
                              {value === undefined
                                ? "—"
                                : value === ""
                                  ? "（空白）"
                                  : typeof value === "number"
                                    ? money(value)
                                    : value}
                            </span>
                          </td>
                        );
                      })}
                      <td>
                        {issue ? (
                          <div className="row-issues">
                            {issues.map((i) => (
                              <button
                                key={i.id}
                                className={`status issue-button ${repeatState(i) === "new" ? "warning" : "bad"}`}
                                onClick={() => updateParams({ issue: i.id })}
                                aria-label={`查看 ${row.id} ${i.ruleId} 錯誤`}
                              >
                                {repeatState(i) !== "new" ? (
                                  <RotateCcw size={12} />
                                ) : (
                                  <AlertCircle size={12} />
                                )}
                                {stateLabel(i)}
                                {issues.length > 1 && ` ${i.ruleId}`}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span
                            className={`status ${notEvaluated ? "" : "good"}`}
                          >
                            <Check size={13} />
                            {notEvaluated ? "尚有未評估" : "通過"}
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
              顯示 {visibleRows.length} / {version.rows.length} 筆資料
            </span>
            <span>
              {version.rows[0] && isTextRow(version.rows[0])
                ? "原始文字與前置零保留"
                : "金額單位：新臺幣元"}
            </span>
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
            files={version.files}
            reportId={report.id}
            versions={report.versions}
            versionId={version.id}
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
            版已通過目前適用檢核。請確認您已核對來源資料與報表內容。
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
