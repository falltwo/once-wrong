import type { Issue, ReportRow, TextDataRow } from "../types";

export const isTextRow = (row: ReportRow): row is TextDataRow =>
  "values" in row;
export const rowValues = (row: ReportRow): Record<string, string | number> =>
  isTextRow(row)
    ? row.values
    : {
        id: row.id,
        product: row.product,
        previous: row.previous,
        opening: row.opening,
      };
export const repeatState = (issue: Issue) =>
  issue.repeatStatus ?? (issue.repeated ? "repeated" : "new");
export const stateLabel = (issue: Issue) =>
  ({
    new: "新錯誤",
    repeated: "重複錯誤",
    regressed: "修好後復發",
  })[repeatState(issue)];
export const issueTouchesRow = (issue: Issue, row: ReportRow) => {
  if (issue.cells?.length)
    return issue.cells.some((cell) => {
      if (isTextRow(row) && cell.fileId && row.fileId) {
        return cell.fileId === row.fileId && cell.row === row.row;
      }
      return cell.rowId === row.id;
    });
  return issue.rowId === row.id || issue.rowIds?.includes(row.id) === true;
};
export const fieldLabel = (column: string) =>
  (
    ({
      id: "資料 ID",
      product: "險種",
      previous: "上月期末",
      opening: "本月期初",
    }) as Record<string, string>
  )[column] ?? column;
