import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSpreadsheet } from "lucide-react";
import { reportsApi } from "../api/reports";
import { Loading, ErrorState } from "../components/QueryStates";

export function ReportsPage() {
  const query = useQuery({ queryKey: ["reports"], queryFn: reportsApi.list });
  return (
    <main>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR REPORTS</div>
          <h1>報表工作空間</h1>
          <p>檢視資料品質，追蹤每一次修正。</p>
        </div>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : (
        <>
          <div className="section-line">
            <h2>最近的報表</h2>
            <span>{query.data.length} 份報表</span>
          </div>
          {query.data.map((report) => {
            const latest = report.versions.at(-1)!;
            return (
              <Link
                key={report.id}
                to={`/reports/${report.id}`}
                className="report-card"
              >
                <span className="report-icon">
                  <FileSpreadsheet size={28} />
                </span>
                <div>
                  <h2>{report.name}</h2>
                  <p>
                    {report.period} · 第 {latest.number} 版 ·{" "}
                    {latest.rows.length} 筆資料
                  </p>
                </div>
                <span
                  className={`status ${latest.issues.length ? "bad" : "good"}`}
                >
                  {latest.issues.length
                    ? `${latest.issues.length} 項待修正`
                    : "全部通過"}
                </span>
                <ArrowRight size={20} />
              </Link>
            );
          })}
          <p className="muted intro-note">
            目前提供一份示範月報。進入工作區後，可上傳 CSV 建立新的報表版本。
          </p>
        </>
      )}
    </main>
  );
}
