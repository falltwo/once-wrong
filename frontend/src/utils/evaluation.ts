import type { Evaluation } from "../types";

const recordedMetrics = [
  ["endToEndHandledCorrectly", "端到端處理正確", "全部錯誤；包含模型呼叫失敗"],
  ["modelResponseAvailable", "模型回覆可用率", "全部錯誤；包含模型呼叫失敗"],
  ["llmErrors", "模型呼叫失敗", "全部錯誤"],
  ["handledCorrectly", "取得模型回覆後處理正確", "排除模型呼叫失敗"],
  [
    "restoredWhenInferable",
    "可推得出時修回正確值",
    "已取得回覆且可推得出原值的錯誤",
  ],
  [
    "heldBackWhenNotInferable",
    "證據不足時保留修法",
    "已取得回覆且無法推得出原值的錯誤",
  ],
  ["citedRule", "引用規則", "已取得模型回覆的錯誤"],
] as const;

/** Preserve each recorded denominator; do not substitute conditional legacy rates. */
export function evaluationMetrics(metrics: Evaluation["metrics"]) {
  return recordedMetrics.flatMap(([key, label, basis]) => {
    const metric = metrics[key];
    return metric ? [{ key, label, basis, metric }] : [];
  });
}
