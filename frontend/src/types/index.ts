export interface DataRow {
  id: string;
  product: string;
  previous: number;
  opening: number;
}
export interface Issue {
  id: string;
  ruleId: string;
  rowId: string;
  field: "opening" | "product";
  title: string;
  actual: string | number;
  expected?: number;
  repeated: boolean;
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
  rows: DataRow[];
  issues: Issue[];
  schemaProfileId?: string;
  ruleVersion?: string;
  validationStatus?: "completed";
  validationRunId?: string;
  sourceSha256?: string;
  summary?: ValidationSummary;
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
