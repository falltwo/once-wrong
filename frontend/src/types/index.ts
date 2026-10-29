export interface DataRow {
  id: string;
  product: string;
  previous: number;
  opening: number;
}
export interface TextDataRow {
  id: string;
  row: number;
  values: Record<string, string>;
  fileId?: string;
  datasetType?: string;
}
export type ReportRow = DataRow | TextDataRow;
export type RepeatStatus = "new" | "repeated" | "regressed";
export interface IssueCell {
  row: number;
  rowId: string;
  column: string;
  value: string | number | null;
  fileId?: string;
  datasetType?: string;
}
export interface Issue {
  id: string;
  ruleId: string;
  rowId?: string;
  rowIds?: string[];
  rows?: number[];
  field?: string;
  title: string;
  actual?: string | number;
  expected?: number;
  repeated: boolean;
  issueKey?: string;
  repeatStatus?: RepeatStatus;
  firstSeenNumber?: number;
  prevSeenNumber?: number | null;
  severity?: "error" | "warning";
  cells?: IssueCell[];
  facts?: Record<string, string | number | null>;
  contextRowIds?: string[];
}
// Optional only so the original frontend demo fixtures still type-check.
// HTTP backend responses always include these metadata and summary fields.
export interface ValidationSummary {
  totalChecks: number;
  passedChecks: number;
  failedChecks: number;
  notEvaluatedChecks: number;
}
export interface Version {
  id: string;
  number: number;
  filename: string;
  createdAt: string;
  rows: ReportRow[];
  issues: Issue[];
  columns?: string[];
  files?: VersionFile[];
  schemaProfileId?: string;
  ruleVersion?: string;
  validationStatus?: "completed";
  validationRunId?: string;
  sourceSha256?: string;
  summary?: ValidationSummary;
  evidence?: {
    notice?: string;
    notEvaluated?: Array<{ code: string; reason: string; checks: number }>;
  };
}
export interface VersionFile {
  id: string;
  datasetType: string;
  filename: string;
  sourceSha256: string;
  columns: string[];
  rows: TextDataRow[];
}
export interface Report {
  id: string;
  name: string;
  period: string;
  versions: Version[];
  submittedVersionId?: string;
  canSubmit?: boolean;
}
export interface Suggestion {
  title: string;
  explanation: string;
  suggestion?: {
    reason: string;
    verification: "passed";
    changes: Array<{
      rowId: string;
      row: number;
      column: string;
      value: string | number | null;
      fileId?: string;
      datasetType?: string;
    }>;
  } | null;
  rejectedSuggestions: string[];
  citations: Array<{
    id: string;
    source: string;
    section: string[];
    page?: number | null;
  }>;
  blockedNumbers: string[];
  model: string;
  verification: "passed" | "unavailable";
  source: "ai" | "fallback_llm_error" | "fallback_number_guard";
}
export interface EvaluationMetric {
  count: number;
  total: number;
  rate: number;
}
export interface Evaluation {
  model: string;
  generatedAt?: string;
  dataset?: { description?: string; cases?: number; violations?: number };
  metrics: Record<string, EvaluationMetric>;
  evaluationContext: {
    evaluatedModel: string;
    runtimeModel: string;
    runtimeConfigured: boolean;
    modelMatchesRuntime: boolean;
    displayNotice: string;
  };
}
