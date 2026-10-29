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
  return [
    {
      id: "reserve-202609",
      name: "準備金月報",
      period: "2026-09",
      versions: [
        {
          id: "v1",
          number: 1,
          filename: "reserve_202609_v1.csv",
          createdAt: "2026-10-24T09:30:00+08:00",
          rows: firstRows,
          issues: firstIssues,
        },
        {
          id: "v2",
          number: 2,
          filename: "reserve_202609_v2.csv",
          createdAt: "2026-10-24T10:15:00+08:00",
          rows,
          issues: validate(rows, firstIssues),
        },
      ],
    },
  ];
}
