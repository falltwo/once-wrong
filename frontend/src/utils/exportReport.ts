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
        manifestSha256: version.manifestSha256,
        summary: version.summary,
        evidence: version.evidence,
        files: version.files?.map((file) => ({
          id: file.id,
          datasetType: file.datasetType,
          filename: file.filename,
          sourceSha256: file.sourceSha256,
          columns: file.columns,
          rowCount: file.rows.length,
          eventDateColumn: file.eventDateColumn,
        })),
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
