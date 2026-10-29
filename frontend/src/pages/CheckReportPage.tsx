import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  ChevronRight,
  FileCheck2,
  History,
} from "lucide-react";
import { reportsApi } from "../api/reports";
import { Loading, ErrorState } from "../components/QueryStates";
import { exportReport } from "../utils/exportReport";
import { date } from "../utils/format";
import { repeatState, stateLabel } from "../utils/issues";

export function CheckReportPage() {
  const { reportId = "" } = useParams();
  const [params] = useSearchParams();
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
  const report = query.data;
  const version =
    report.versions.find((v) => v.id === params.get("version")) ??
    report.versions.at(-1)!;
  return (
    <main>
      <Link
        className="back-link"
        to={`/reports/${report.id}?version=${version.id}`}
      >
        <ArrowLeft size={14} />
        返回檢核工作區
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">VALIDATION RECORD</div>
          <h1>檢核報告與版本紀錄</h1>
          <p>
            {report.period} {report.name} · 後端檢核結果
          </p>
        </div>
        <button
          className="secondary"
          onClick={() => exportReport(report, version)}
        >
          <ArrowDownToLine size={16} />
          下載第 {version.number} 版報告
        </button>
      </div>
      <section className="record-sheet">
        <h2>
          <FileCheck2 size={20} />第 {version.number} 版檢核摘要
        </h2>
        <p>
          {version.filename} · {date(version.createdAt)}
        </p>
        {!!version.summary?.notEvaluatedChecks && (
          <p className="text-orange">
            另有 {version.summary.notEvaluatedChecks} 項未評估，不能視為通過。
          </p>
        )}
        {version.files && (
          <div className="version-files">
            {version.files.map((file) => (
              <a
                key={file.id}
                href={reportsApi.sourceUrl(version.id, file.id)}
                download
              >
                {file.datasetType} · {file.filename}
              </a>
            ))}
          </div>
        )}
        <p>
          資料共 {version.rows.length} 筆，執行{" "}
          {version.summary?.totalChecks ?? "—"} 項檢核，其中{" "}
          {version.summary?.failedChecks ?? "—"} 項未通過。
        </p>
        {version.issues.map((issue) => (
          <div className="record-issue" key={issue.id}>
            <span className="rule-tag">{issue.ruleId}</span>
            <strong>
              {issue.rowId ??
                issue.rowIds?.join("、") ??
                issue.cells
                  ?.map((cell) => `${cell.fileId ?? ""} 第${cell.row}列`)
                  .join("、")}
            </strong>
            <span>{issue.title}</span>
            <span
              className={`status ${repeatState(issue) === "new" ? "warning" : "bad"}`}
            >
              {stateLabel(issue)}
            </span>
          </div>
        ))}
        {version.validationStatus === "completed" &&
          !version.issues.length &&
          !version.summary?.notEvaluatedChecks && (
            <p className="text-green">目前適用檢核通過。</p>
          )}
      </section>
      <div className="section-line">
        <h2>版本歷程</h2>
        <span>{report.versions.length} 個版本</span>
      </div>
      <div className="history-list">
        {[...report.versions].reverse().map((v) => (
          <Link key={v.id} to={`/reports/${report.id}?version=${v.id}`}>
            <span className="history-icon">
              <History size={18} />
            </span>
            <div>
              <strong>第 {v.number} 版</strong>
              <p>
                {v.filename} · {date(v.createdAt)}
              </p>
            </div>
            <span className={`status ${v.issues.length ? "bad" : "good"}`}>
              {v.issues.length
                ? `${v.issues.length} 項錯誤`
                : v.summary?.notEvaluatedChecks
                  ? "尚有未評估"
                  : "全部通過"}
            </span>
            <ChevronRight size={16} />
          </Link>
        ))}
      </div>
    </main>
  );
}
