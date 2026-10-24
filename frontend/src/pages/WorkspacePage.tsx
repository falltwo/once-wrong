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
  const submitted = report.submittedVersionId === version.id;
  const canSubmit =
    version.id === latest.id && !version.issues.length && !submitted;
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
    const issues = version.issues.filter((i) => i.rowId === row.id);
    return (
      (filter === "all" ||
        (filter === "errors" && issues.length) ||
        (filter === "repeated" && issues.some((i) => i.repeated))) &&
      `${row.id} ${row.product}`.toLowerCase().includes(search.toLowerCase())
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
            {version.rows.length * 2 - version.issues.length}
            <small>項</small>
          </strong>
          <p>共執行 {version.rows.length * 2} 項規則檢查</p>
        </div>
        <div>
          <span>待修正</span>
          <strong className="text-red">
            {version.issues.length}
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
        className={`notice ${version.issues.length ? "blocked" : "passed"}`}
        role="status"
      >
        {version.issues.length ? (
          <LockKeyhole size={20} />
        ) : (
          <CircleCheck size={20} />
        )}
        <div>
          <strong>
            {submitted
              ? "已完成模擬送出"
              : version.id !== latest.id
                ? "正在檢視歷史版本"
                : version.issues.length
                  ? "送出已鎖定，請先完成修正"
                  : "所有示範檢核已通過"}
          </strong>
          <p>
            {version.id !== latest.id
              ? "請切換到最新版本進行送出確認。"
              : submitted
                ? "確認紀錄已保存在此瀏覽器，未送往外部申報系統。"
                : repeated
                  ? `有 ${repeated} 項錯誤在前後兩版都未通過，請依檢核說明核對來源資料。`
                  : version.issues.length
                    ? "修改資料並重新上傳，系統會再次檢查。"
                    : "請完成最後人工確認，再進行模擬送出。"}
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
                ["repeated", "重複錯誤"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={filter === value}
                  className={filter === value ? "selected" : ""}
                  onClick={() => updateParams({ filter: value })}
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
                  <th>險種</th>
                  <th className="number">上月期末</th>
                  <th className="number">本月期初</th>
                  <th>檢核狀態</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const issues = version.issues.filter(
                    (i) => i.rowId === row.id,
                  );
                  const issue = issues[0];
                  return (
                    <tr
                      key={row.id}
                      className={
                        selected?.rowId === row.id ? "selected-row" : ""
                      }
                    >
                      <td className="row-id">{row.id}</td>
                      <td className={!row.product ? "invalid-cell" : ""}>
                        {row.product || "（空白）"}
                      </td>
                      <td className="number">{money(row.previous)}</td>
                      <td
                        className={`number ${issues.some((i) => i.field === "opening") ? "invalid-cell" : ""}`}
                      >
                        {money(row.opening)}
                      </td>
                      <td>
                        {issue ? (
                          <div className="row-issues">
                            {issues.map((i) => (
                              <button
                                key={i.id}
                                className={`status issue-button ${i.repeated ? "bad" : "warning"}`}
                                onClick={() => updateParams({ issue: i.id })}
                                aria-label={`查看 ${row.id} ${i.ruleId} 錯誤`}
                              >
                                {i.repeated ? (
                                  <RotateCcw size={12} />
                                ) : (
                                  <AlertCircle size={12} />
                                )}
                                {i.repeated ? "重複錯誤" : "待修正"}
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
              顯示 {visibleRows.length} / {version.rows.length} 筆資料
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
          {submitted ? "已模擬送出" : "確認送出（模擬）"}
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
          title="確認模擬送出"
          onClose={() => setConfirm(false)}
          busy={submit.isPending}
        >
          <p>
            第 {version.number}{" "}
            版已通過示範規則。請確認您已核對來源資料與報表內容。
          </p>
          <p className="muted">
            此操作只記錄本機確認狀態，不會送往任何外部申報系統。
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
              {submit.isPending ? "確認中…" : "已核對，確認送出"}
            </button>
          </div>
        </Dialog>
      )}
    </main>
  );
}
