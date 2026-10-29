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
import {
  fileLabel,
  issueLocation,
  issueStatus,
  statusClass,
  statusLabel,
} from "../utils/reportData";

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
            {report.period} {report.name} · {version.schemaProfileId} /{" "}
            {version.ruleVersion}
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
        {version.files?.length ? (
          <ul className="record-files">
            {version.files.map((file) => (
              <li key={file.id}>
                <strong>{fileLabel(file)}</strong> · {file.filename} ·{" "}
                {file.rows.length} 筆
                <a href={reportsApi.sourceUrl(version.id, file.id)} download>
                  下載來源檔
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p>
            <a href={reportsApi.sourceUrl(version.id)} download>
              下載原始檔
            </a>
          </p>
        )}
        <p>
          資料共 {version.rows.length} 筆，執行{" "}
          {version.summary?.totalChecks ?? "—"} 項檢核，其中{" "}
          {version.summary?.failedChecks ?? "—"} 項未通過，未執行{" "}
          {version.summary?.notEvaluatedChecks ?? "—"} 項。
        </p>
        {version.evidence?.notEvaluated?.map((item, index) => (
          <p className="neutral-notice" key={`${item.code}:${index}`}>
            {item.code}：{item.reason}（{item.checks} 項）
          </p>
        ))}
        {version.issues.map((issue) => (
          <div className="record-issue" key={issue.id}>
            <span className="rule-tag">{issue.ruleId}</span>
            <strong>{issueLocation(issue)}</strong>
            <span>{issue.title}</span>
            <span className={`status ${statusClass(issueStatus(issue))}`}>
              {statusLabel(issueStatus(issue))}
            </span>
          </div>
        ))}
        {version.validationStatus === "completed" &&
          !version.issues.length &&
          !version.summary?.notEvaluatedChecks && (
            <p className="text-green">所有示範檢核通過。</p>
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
              {v.issues.length ? `${v.issues.length} 項錯誤` : "全部通過"}
            </span>
            <ChevronRight size={16} />
          </Link>
        ))}
      </div>
    </main>
  );
}
