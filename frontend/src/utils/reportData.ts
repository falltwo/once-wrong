import type {
  CellValue,
  DataRow,
  Issue,
  RepeatStatus,
  VersionFile,
} from "../types";

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

export const datasetLabels: Record<string, string> = {
  underwriting: "承保檔",
  claims: "給付檔",
  subjects: "填報對象檔",
};

export function fileLabel(file: VersionFile): string {
  return datasetLabels[file.datasetType] ?? file.datasetType;
}

export function rowFileId(row: DataRow): string | undefined {
  return "values" in row ? row.fileId : undefined;
}

export function rowDatasetType(row: DataRow): string | undefined {
  return "values" in row ? row.datasetType : undefined;
}

export function rowValues(row: DataRow): Record<string, CellValue> {
  if ("values" in row) return row.values;
  return {
    product: row.product,
    previous: row.previous,
    opening: row.opening,
  };
}

export function rowLabel(row: DataRow): string {
  if (!("row" in row)) return row.id;
  const file = row.datasetType
    ? `${datasetLabels[row.datasetType] ?? row.datasetType} · `
    : "";
  return `${file}第 ${row.row} 列`;
}

export function issueRowIds(issue: Issue): string[] {
  if (issue.rowIds?.length) return issue.rowIds;
  return issue.rowId ? [issue.rowId] : [];
}

export function issueAffectsRow(issue: Issue, row: DataRow): boolean {
  if (issueRowIds(issue).includes(row.id)) return true;
  if (issue.cells?.some((cell) => cell.rowId === row.id)) return true;
  if (!("row" in row)) return issue.rowId === row.id;
  const hasQualifiedIdentity = Boolean(
    issue.rowIds?.length || issue.cells?.length,
  );
  if (hasQualifiedIdentity) return false;
  return Boolean(issue.rows?.includes(row.row));
}

export function issueAffectsCell(
  issue: Issue,
  row: DataRow,
  column: string,
): boolean {
  if (
    issue.cells?.some(
      (cell) =>
        cell.rowId === row.id &&
        cell.column === column &&
        (!cell.fileId || !rowFileId(row) || cell.fileId === rowFileId(row)),
    )
  )
    return true;
  return issue.rowId === row.id && issue.field === column;
}

export function issueStatus(issue: Issue): RepeatStatus {
  return issue.repeatStatus ?? (issue.repeated ? "repeated" : "new");
}

export function statusLabel(status: RepeatStatus): string {
  return {
    new: "新錯誤",
    repeated: "持續錯誤",
    regressed: "修正後復發",
  }[status];
}

export function statusClass(status: RepeatStatus): string {
  return status === "repeated"
    ? "bad"
    : status === "regressed"
      ? "regressed"
      : "warning";
}

export function issueAffectsFile(issue: Issue, fileId: string): boolean {
  return Boolean(
    issue.cells?.some((cell) => cell.fileId === fileId) ||
    issue.rowIds?.some((rowId) => rowId.startsWith(`${fileId}:`)) ||
    issue.contextRowIds?.some((rowId) => rowId.startsWith(`${fileId}:`)),
  );
}

export function formatCell(value: CellValue): string {
  return value === null || value === "" ? "（空白）" : String(value);
}

export function issueLocation(issue: Issue): string {
  if (issue.cells?.length) {
    const locations = [
      ...new Set(
        issue.cells.map((cell) =>
          cell.datasetType
            ? `${datasetLabels[cell.datasetType] ?? cell.datasetType} · ${cell.rowId}`
            : cell.rowId,
        ),
      ),
    ];
    return locations.join("、");
  }
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
      const key = `${cell.fileId ?? ""}:${cell.rowId}:${cell.column}`;
      if (seen.has(key)) return [];
      seen.add(key);
      const file = cell.datasetType
        ? `${datasetLabels[cell.datasetType] ?? cell.datasetType} · `
        : "";
      return [
        [`${file}${cell.rowId} · ${cell.column}`, cell.value] as [
          string,
          CellValue,
        ],
      ];
    });
  }
  return issue.field ? [[issue.field, issue.actual ?? null]] : [];
}
