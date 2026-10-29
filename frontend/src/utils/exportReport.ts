import { download } from "../api/reports";
import type { Report, Version } from "../types";

export function exportReport(report: Report, version: Version) {
  download(
    `OnceWrong-${report.period}-v${version.number}.json`,
    JSON.stringify(
      {
        mode: "backend-demo",
        reportId: report.id,
        versionId: version.id,
        schemaProfileId: version.schemaProfileId,
        ruleVersion: version.ruleVersion,
        validationStatus: version.validationStatus,
        validationRunId: version.validationRunId,
        sourceSha256: version.sourceSha256,
        summary: version.summary,
        internallyConfirmed: report.submittedVersionId === version.id,
        report: report.name,
        period: report.period,
        version: version.number,
        filename: version.filename,
        generatedAt: new Date().toISOString(),
        totalRows: version.rows.length,
        issues: version.issues,
      },
      null,
      2,
    ),
    "application/json;charset=utf-8",
  );
}
