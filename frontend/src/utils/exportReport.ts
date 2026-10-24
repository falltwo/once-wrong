import { download } from "../api/reports";
import type { Report, Version } from "../types";

export function exportReport(report: Report, version: Version) {
  download(
    `OnceWrong-${report.period}-v${version.number}.json`,
    JSON.stringify(
      {
        mode: "demo",
        report: report.name,
        period: report.period,
        version: version.number,
        filename: version.filename,
        generatedAt: new Date().toISOString(),
        rules: ["R-01 險種不可空白", "R-07 期初等於上期末"],
        totalRows: version.rows.length,
        issues: version.issues,
      },
      null,
      2,
    ),
    "application/json;charset=utf-8",
  );
}
