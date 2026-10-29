import type { CellValue, DataRow, Issue } from "../types";

export const lifeFieldLabels: Record<string, string> = {
  公司代號: "公司代號",
  保單編號: "保單編號",
  保單編號序號: "保單編號序號",
  異動序號: "異動序號",
  加保別: "加保別",
  加保日期: "加保日期",
  退保別: "退保別",
  退保日期: "退保日期",
};

export function rowValues(row: DataRow): Record<string, CellValue> {
  if (row.values) return row.values;
  return {
    product: row.product ?? "",
    previous: row.previous ?? null,
    opening: row.opening ?? null,
  };
}

export function rowLabel(row: DataRow): string {
  return row.row === undefined ? row.id : `第 ${row.row} 列`;
}

export function issueRowIds(issue: Issue): string[] {
  if (issue.rowIds?.length) return issue.rowIds;
  return issue.rowId ? [issue.rowId] : [];
}

export function issueAffectsRow(issue: Issue, row: DataRow): boolean {
  if (issueRowIds(issue).includes(row.id)) return true;
  return row.row !== undefined && Boolean(issue.rows?.includes(row.row));
}

export function issueAffectsCell(
  issue: Issue,
  row: DataRow,
  column: string,
): boolean {
  if (issue.cells?.some((cell) => cell.rowId === row.id && cell.column === column))
    return true;
  return issue.rowId === row.id && issue.field === column;
}

export function formatCell(value: CellValue): string {
  return value === null || value === "" ? "（空白）" : String(value);
}

export function issueLocation(issue: Issue): string {
  const ids = issueRowIds(issue);
  return ids.length ? ids.map((id) => `資料 ${id}`).join("、") : "相關資料列";
}

export function issueFacts(issue: Issue): Array<[string, CellValue]> {
  if (issue.facts && Object.keys(issue.facts).length) {
    return Object.entries(issue.facts);
  }
  if (issue.cells?.length) {
    const seen = new Set<string>();
    return issue.cells.flatMap((cell) => {
      const key = `${cell.rowId}:${cell.column}`;
      if (seen.has(key)) return [];
      seen.add(key);
      return [[`${cell.rowId} · ${cell.column}`, cell.value] as [string, CellValue]];
    });
  }
  return issue.field ? [[issue.field, issue.actual ?? null]] : [];
}
