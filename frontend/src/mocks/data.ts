import type { DataRow, Report } from "../types";
import { validate } from "../features/validation/rules";

const rows: DataRow[] = [
  { id: "POL-001", product: "CR-01", previous: 9812400, opening: 9812400 },
  { id: "POL-002", product: "CR-02", previous: 4105000, opening: 4105000 },
  { id: "POL-003", product: "ML-05", previous: 12480000, opening: 12005000 },
  { id: "POL-004", product: "", previous: 1020300, opening: 1020300 },
  { id: "POL-005", product: "WL-02", previous: 7340000, opening: 7340000 },
  { id: "POL-006", product: "AN-03", previous: 2560000, opening: 2560000 },
];
export function initialReports(): Report[] {
  const firstRows = rows.map((r) => ({
    ...r,
    product: r.id === "POL-004" ? "CR-04" : r.product,
    opening: r.id === "POL-001" ? 9800000 : r.opening,
  }));
  const firstIssues = validate(firstRows);
  const makeVersion = (
    id: string,
    number: number,
    filename: string,
    createdAt: string,
    versionRows: DataRow[],
    issues: ReturnType<typeof validate>,
  ) => ({
    id,
    number,
    filename,
    createdAt,
    rows: versionRows,
    issues,
    schemaProfileId: "demo_csv_v1" as const,
    ruleVersion: "demo_rules_v1" as const,
    validationStatus: "completed" as const,
    validationRunId: `mock-run-${id}`,
    sourceSha256: "mock-data-not-a-source-file-hash",
    summary: {
      totalChecks: versionRows.length * 2,
      passedChecks: versionRows.length * 2 - issues.length,
      failedChecks: issues.length,
      notEvaluatedChecks: 0,
    },
  });
  return [
    {
      id: "reserve-202609",
      name: "準備金月報",
      period: "2026-09",
      versions: [
        makeVersion(
          "v1",
          1,
          "reserve_202609_v1.csv",
          "2026-10-24T09:30:00+08:00",
          firstRows,
          firstIssues,
        ),
        makeVersion(
          "v2",
          2,
          "reserve_202609_v2.csv",
          "2026-10-24T10:15:00+08:00",
          rows,
          validate(rows, firstIssues),
        ),
      ],
      canSubmit: false,
    },
  ];
}
