import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChartNoAxesCombined,
  CircleHelp,
  FileCheck2,
  FlaskConical,
} from "lucide-react";
import { reportsApi } from "../api/reports";
import { ErrorState, Loading } from "../components/QueryStates";
import type { EvaluationMetric } from "../types";

const percent = (rate: number | null) =>
  rate === null ? "—" : `${(rate * 100).toFixed(1)}%`;

function MetricCard({
  title,
  metric,
}: {
  title: string;
  metric: EvaluationMetric;
}) {
  return (
    <article className="method-card">
      <div className="method-name">
        <span className="method-dot" />
        <h3>{title}</h3>
      </div>
      <div className="metric-row">
        <div>
          <span>比例</span>
          <strong>{percent(metric.rate)}</strong>
        </div>
        <div>
          <span>筆數</span>
          <strong className="rule-version">
            {metric.count} / {metric.total}
          </strong>
        </div>
      </div>
      <div className="metric-bars">
        <div>
          <span>結果</span>
          <div className="bar-track">
            <div
              className="bar-fill precision-fill"
              style={{ width: percent(metric.rate) }}
            />
          </div>
          <b>{percent(metric.rate)}</b>
        </div>
      </div>
    </article>
  );
}

export function TestResultsPage() {
  const overviewQuery = useQuery({
    queryKey: ["backend-validation-overview"],
    queryFn: async () => {
      const [health, reports] = await Promise.all([
        reportsApi.health(),
        reportsApi.list(),
      ]);
      return { health, reports };
    },
  });
  const evaluationQuery = useQuery({
    queryKey: ["backend-evaluation"],
    queryFn: reportsApi.evaluationLatest,
    retry: false,
  });

  if (overviewQuery.isPending) {
    return (
      <main>
        <Loading />
      </main>
    );
  }
  if (overviewQuery.isError) {
    return (
      <main>
        <ErrorState error={overviewQuery.error} retry={() => overviewQuery.refetch()} />
      </main>
    );
  }

  const { health, reports } = overviewQuery.data;
  const latestReports = reports.flatMap((report) => {
    const version = report.versions.at(-1);
    return version ? [{ report, version }] : [];
  });
  const totals = latestReports.reduce(
    (result, { version }) => ({
      rows: result.rows + version.rows.length,
      checks: result.checks + version.summary.totalChecks,
      passed: result.passed + version.summary.passedChecks,
      failed: result.failed + version.summary.failedChecks,
      notEvaluated: result.notEvaluated + version.summary.notEvaluatedChecks,
    }),
    { rows: 0, checks: 0, passed: 0, failed: 0, notEvaluated: 0 },
  );
  const evaluation = evaluationQuery.data;
  const generatedDate = evaluation
    ? new Intl.DateTimeFormat("zh-TW", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Taipei",
      }).format(new Date(evaluation.generatedAt))
    : undefined;

  return (
    <main className="evaluation-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">BACKEND EVALUATION</div>
          <h1>測試結果</h1>
          <p>分開呈現實際報表檢核與 AI 審核建議評測。</p>
        </div>
        <span className="benchmark-badge">
          <FlaskConical size={15} />
          {health.schemaProfileId} · {health.ruleVersion}
        </span>
      </div>

      <section className="prototype-warning" role="note" aria-label="評測資料說明">
        <AlertTriangle size={20} />
        <div>
          <strong>
            {evaluation
              ? "AI 審核分數來自後端評測快照，不是抓錯 Precision / Recall"
              : "目前後端沒有可讀取的 AI 評測快照"}
          </strong>
          <p>
            {evaluation
              ? `評測使用程式產生的虛構${evaluation.dataset.product}資料與 ${evaluation.dataset.rules}，模型為 ${evaluation.model}；不能解讀為正式資料上的模型成績。`
              : "請確認後端已設定 ONCE_WRONG_EVALUATION，並提供有效的評測 JSON。"}
          </p>
        </div>
      </section>

      {evaluationQuery.isError && (
        <div className="neutral-notice" role="status">
          評測 API 暫不可用：{evaluationQuery.error.message}
          <button className="text-button" onClick={() => evaluationQuery.refetch()}>
            重試
          </button>
        </div>
      )}

      {evaluation && (
        <>
          <section className="benchmark-setup" aria-labelledby="evaluation-data-title">
            <div className="setup-title">
              <span>
                <FlaskConical size={17} />
              </span>
              <div>
                <h2 id="evaluation-data-title">AI 評測資料</h2>
                <p>
                  {evaluation.model} · 產生於 {generatedDate} · {evaluation.dataset.rules}
                </p>
              </div>
            </div>
            <div className="setup-stats">
              <div>
                <span>案例數</span>
                <strong>{evaluation.dataset.cases}</strong>
              </div>
              <div>
                <span>違規數</span>
                <strong className="text-red">{evaluation.dataset.violations}</strong>
              </div>
              <div>
                <span>測試輪次</span>
                <strong>{evaluation.runs.length}</strong>
              </div>
              <div>
                <span>資料類型</span>
                <strong className="setup-methods">{evaluation.dataset.product}</strong>
              </div>
            </div>
          </section>

          <div className="section-line evaluation-heading">
            <h2>
              <ChartNoAxesCombined size={18} />
              AI 審核表現
            </h2>
            <span>以 {evaluation.dataset.violations} 筆違規為評測分母</span>
          </div>
          <section className="method-cards" aria-label="AI 審核評測指標">
            <MetricCard title="正確處理違規" metric={evaluation.metrics.handledCorrectly} />
            <MetricCard title="可推知時還原正確值" metric={evaluation.metrics.restoredWhenInferable} />
            <MetricCard title="無法推知時不亂猜" metric={evaluation.metrics.heldBackWhenNotInferable} />
            <MetricCard title="引用對應規則" metric={evaluation.metrics.citedRule} />
          </section>

          <section className="confusion-section">
            <div className="section-line">
              <h2>各規則評測結果</h2>
              <span>{evaluation.byRule.length} 條規則</span>
            </div>
            <div className="table-panel confusion-table-wrap">
              <div className="table-scroll">
                <table className="confusion-table">
                  <thead>
                    <tr>
                      <th>規則</th>
                      <th className="number">違規數</th>
                      <th className="number">正確處理</th>
                      <th className="number">可推知時還原</th>
                      <th className="number">不可推知時保留</th>
                      <th className="number">引用規則</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluation.byRule.map((rule) => (
                      <tr key={rule.ruleId}>
                        <td><strong>{rule.ruleId}</strong></td>
                        <td className="number">{rule.violations}</td>
                        <td className="number">{percent(rule.handledCorrectly.rate)}</td>
                        <td className="number">{percent(rule.restoredWhenInferable.rate)}</td>
                        <td className="number">{percent(rule.heldBackWhenNotInferable.rate)}</td>
                        <td className="number">{percent(rule.citedRule.rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="matrix-note">
              <CircleHelp size={14} />
              後端沒有提供 ground truth 的規則抓錯 TP / FP / FN，因此此頁不計算 Precision、Recall 或 Accuracy。
            </p>
          </section>
        </>
      )}

      <div className="section-line evaluation-heading">
        <h2>
          <FileCheck2 size={18} />
          使用者報表檢核概況
        </h2>
        <span>只統計每份報表的最新版本，不重複加總歷史版本</span>
      </div>
      <section className="benchmark-setup">
        <div className="setup-stats">
          <div><span>報表數</span><strong>{latestReports.length}</strong></div>
          <div><span>資料筆數</span><strong>{totals.rows}</strong></div>
          <div><span>規則檢查</span><strong>{totals.checks}</strong></div>
          <div><span>未通過 / 通過 / 未評估</span><strong>{totals.failed} / {totals.passed} / {totals.notEvaluated}</strong></div>
        </div>
      </section>
      <div className="section-line">
        <h2>各報表最新版</h2>
        <span>{reports.length} 份報表</span>
      </div>
      {latestReports.length ? (
        <div className="table-panel confusion-table-wrap">
          <div className="table-scroll">
            <table className="confusion-table">
              <thead>
                <tr>
                  <th>報表</th>
                  <th>期間</th>
                  <th className="number">版本</th>
                  <th className="number">資料筆數</th>
                  <th className="number">檢查數</th>
                  <th className="number">未通過</th>
                </tr>
              </thead>
              <tbody>
                {latestReports.map(({ report, version }) => (
                  <tr key={report.id}>
                    <td><Link to={`/reports/${report.id}`}><strong>{report.name}</strong></Link></td>
                    <td>{report.period}</td>
                    <td className="number">第 {version.number} 版</td>
                    <td className="number">{version.rows.length}</td>
                    <td className="number">{version.summary.totalChecks}</td>
                    <td className="number">{version.summary.failedChecks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="muted intro-note">目前後端還沒有已完成檢核的報表。</p>
      )}
      <section className="next-metrics">
        <div>
          <div className="next-metrics-icon"><CircleHelp size={18} /></div>
          <div>
            <h2>規則抓錯 Precision / Recall</h2>
            <p>需要後端提供固定測試集的人工標註答案與各規則預測結果。</p>
          </div>
          <span className="pending-metric">尚未提供</span>
        </div>
      </section>
    </main>
  );
}
