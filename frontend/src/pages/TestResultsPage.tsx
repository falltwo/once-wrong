import {
  AlertTriangle,
  ChartNoAxesCombined,
  CircleHelp,
  FlaskConical,
} from "lucide-react";

/** Illustrative values used only to demonstrate the evaluation page layout. */
const examples = [
  {
    name: "只有規則",
    key: "rules",
    tp: 16,
    fp: 4,
    fn: 4,
    tn: 76,
    description: "符合規則的錯誤能穩定抓出；規則外的錯誤不會被發現。",
  },
  {
    name: "只有 AI",
    key: "ai",
    tp: 18,
    fp: 10,
    fn: 2,
    tn: 70,
    description: "抓到較多錯誤，但也把部分正確資料標成錯誤。",
  },
  {
    name: "Once Wrong",
    key: "once-wrong",
    tp: 18,
    fp: 3,
    fn: 2,
    tn: 77,
    description: "AI 協助說明，規則負責重驗建議與攔截重複錯誤。",
  },
];
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const metrics = (tp: number, fp: number, fn: number, tn: number) => ({
  precision: tp / (tp + fp),
  recall: tp / (tp + fn),
  accuracy: (tp + tn) / (tp + fp + fn + tn),
});

export function TestResultsPage() {
  return (
    <main className="evaluation-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">BENCHMARK</div>
          <h1>測試結果</h1>
          <p>用相同且有標準答案的報表，比較不同檢查方式。</p>
        </div>
        <span className="benchmark-badge">
          <FlaskConical size={15} />
          測試設計示意
        </span>
      </div>

      <section className="prototype-warning" role="note" aria-label="數據說明">
        <AlertTriangle size={20} />
        <div>
          <strong>以下數據是介面示意，不是實測成績</strong>
          <p>
            用假設的 100
            筆樣本展示指標如何呈現。完成標註與實驗後，請用真實結果取代；不要引用這些數字作為比賽結論。
          </p>
        </div>
      </section>

      <section className="benchmark-setup" aria-labelledby="setup-title">
        <div className="setup-title">
          <span>
            <FlaskConical size={17} />
          </span>
          <div>
            <h2 id="setup-title">測試資料設定</h2>
            <p>比較前先固定樣本與標準答案，確保三種方式使用同一批資料。</p>
          </div>
        </div>
        <div className="setup-stats">
          <div>
            <span>示例樣本數</span>
            <strong>
              100 <small>筆</small>
            </strong>
          </div>
          <div>
            <span>標準答案為錯誤</span>
            <strong className="text-red">
              20 <small>筆</small>
            </strong>
          </div>
          <div>
            <span>標準答案為正確</span>
            <strong>
              80 <small>筆</small>
            </strong>
          </div>
          <div>
            <span>對照組</span>
            <strong className="setup-methods">
              3 <small>種方式</small>
            </strong>
          </div>
        </div>
      </section>

      <div className="section-line evaluation-heading">
        <h2>
          <ChartNoAxesCombined size={18} />
          偵錯能力比較
        </h2>
        <span>示例結果 · 分母以同一批 100 筆資料計算</span>
      </div>
      <section
        className="method-cards"
        aria-label="各方法的 precision 與 recall 比較"
      >
        {examples.map((example) => {
          const result = metrics(
            example.tp,
            example.fp,
            example.fn,
            example.tn,
          );
          return (
            <article className={`method-card ${example.key}`} key={example.key}>
              <div className="method-name">
                <span className="method-dot" />
                <h3>{example.name}</h3>
                {example.key === "once-wrong" && (
                  <span className="method-label">組合方式</span>
                )}
              </div>
              <p>{example.description}</p>
              <div className="metric-row">
                <div>
                  <span>Precision 精確率</span>
                  <strong>{percent(result.precision)}</strong>
                </div>
                <div>
                  <span>Recall 召回率</span>
                  <strong>{percent(result.recall)}</strong>
                </div>
              </div>
              <div className="metric-bars">
                <div>
                  <span>精確率</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill precision-fill"
                      style={{ width: percent(result.precision) }}
                    />
                  </div>
                  <b>{percent(result.precision)}</b>
                </div>
                <div>
                  <span>召回率</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill recall-fill"
                      style={{ width: percent(result.recall) }}
                    />
                  </div>
                  <b>{percent(result.recall)}</b>
                </div>
              </div>
            </article>
          );
        })}
      </section>

      <section className="confusion-section">
        <div className="section-line">
          <h2>每種方法抓到什麼</h2>
          <span>數值為示意筆數</span>
        </div>
        <div className="table-panel confusion-table-wrap">
          <div className="table-scroll">
            <table className="confusion-table">
              <thead>
                <tr>
                  <th>檢查方式</th>
                  <th className="number">抓到的錯誤 TP</th>
                  <th className="number">誤報 FP</th>
                  <th className="number">漏掉 FN</th>
                  <th className="number">正確放行 TN</th>
                  <th className="number">整體正確率</th>
                </tr>
              </thead>
              <tbody>
                {examples.map(({ name, key, tp, fp, fn, tn }) => {
                  const result = metrics(tp, fp, fn, tn);
                  return (
                    <tr key={key}>
                      <td>
                        <strong>{name}</strong>
                      </td>
                      <td className="number text-green">{tp}</td>
                      <td className="number text-orange">{fp}</td>
                      <td className="number text-red">{fn}</td>
                      <td className="number">{tn}</td>
                      <td className="number">{percent(result.accuracy)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <p className="matrix-note">
          <CircleHelp size={14} />
          TP = 抓到的真錯誤，FP = 把正確資料誤判為錯誤，FN = 漏掉的錯誤，TN =
          正確放行的資料。
        </p>
      </section>

      <section className="next-metrics">
        <div>
          <div className="next-metrics-icon">
            <CircleHelp size={18} />
          </div>
          <div>
            <h2>AI 修正建議正確率</h2>
            <p>需逐筆比對建議值與人工確認的正確值，目前尚無實測資料。</p>
          </div>
          <span className="pending-metric">待測</span>
        </div>
        <div>
          <div className="next-metrics-icon">
            <ChartNoAxesCombined size={18} />
          </div>
          <div>
            <h2>改到全數通過的輪數與處理時間</h2>
            <p>
              使用同一批錯誤報表計時，記錄每種方法完成修正所需的輪數和時間。
            </p>
          </div>
          <span className="pending-metric">待測</span>
        </div>
      </section>

      <div className="methodology-note">
        <strong>計算方式</strong>
        <span>Precision = TP ÷ (TP + FP)</span>
        <span>Recall = TP ÷ (TP + FN)</span>
        <span>整體正確率 = (TP + TN) ÷ 全部樣本</span>
        <p>
          請先標記每筆測試資料的真實狀態，再分別執行三種方式。報告實測結果時，同時列出測試筆數與
          TP、FP、FN、TN，方便評審核對比例。
        </p>
      </div>
    </main>
  );
}
