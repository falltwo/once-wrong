import type { CellValue, DataRow } from "../types";

/** Draft edits are keyed by row id + column; they never touch the stored version. */
export const draftKey = (rowId: string, column: string) => `${rowId}\u0000${column}`;

function csvField(value: CellValue): string {
  const text = value === null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/**
 * Corrected copy of a single-file version for the user to check and re-upload, in the same
 * columns the backend accepts. Returns null for multi-file filings (one file per dataset).
 */
export function correctedCsv(
  rows: DataRow[],
  columns: string[],
  drafts: Record<string, CellValue>,
): string | null {
  if (rows.some((row) => "values" in row && row.fileId)) return null;
  const demo = rows.length > 0 && !("values" in rows[0]);
  const header = demo ? ["id", ...columns] : columns;
  const lines = rows.map((row) => {
    const values: Record<string, CellValue> =
      "values" in row
        ? row.values
        : { product: row.product, previous: row.previous, opening: row.opening };
    const cells = columns.map((column) => {
      const key = draftKey(row.id, column);
      return csvField(key in drafts ? drafts[key] : (values[column] ?? null));
    });
    return (demo ? [csvField(row.id), ...cells] : cells).join(",");
  });
  return `﻿${[header.map(csvField).join(","), ...lines].join("\r\n")}\r\n`;
}
