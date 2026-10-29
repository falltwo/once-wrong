import type { DataRow, Issue } from "../../types";

// 前端展示專用規則。正式環境請以後端檢核結果取代。
export function validate(rows: DataRow[], previous: Issue[] = []): Issue[] {
  const issues: Issue[] = [];
  for (const row of rows) {
    if (row.previous !== row.opening)
      issues.push({
        id: `${row.id}:R-07`,
        ruleId: "R-07",
        rowId: row.id,
        field: "opening",
        title: "期初與上期末金額不一致",
        actual: row.opening,
        expected: row.previous,
        repeated: false,
      });
    if (!(row.product ?? "").trim())
      issues.push({
        id: `${row.id}:R-01`,
        ruleId: "R-01",
        rowId: row.id,
        field: "product",
        title: "險種代碼不可空白",
        actual: "空白",
        repeated: false,
      });
  }
  return issues.map((issue) => ({
    ...issue,
    repeated: previous.some((old) => old.id === issue.id),
  }));
}
