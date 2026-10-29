export type CellValue = string | number | boolean | null;

export interface DataRow {
  id: string;
  /** Life profile row number (1-based data row, not a physical CSV line). */
  row?: number;
  /** Dynamic source columns used by life_underwriting_v1. */
  values?: Record<string, CellValue>;
  /** demo_csv_v1 fields retained for the original demo profile. */
  product?: string;
  previous?: number;
  opening?: number;
}

export interface IssueCell {
  row: number;
  rowId: string;
  column: string;
  value: CellValue;
}

export interface Issue {
  id: string;
  ruleId: string;
  title: string;
  repeated: boolean;
  /** demo_csv_v1 issue fields */
  rowId?: string;
  field?: string;
  actual?: CellValue;
  expected?: CellValue;
  /** life_underwriting_v1 issue fields */
  rows?: number[];
  rowIds?: string[];
  cells?: IssueCell[];
  facts?: Record<string, CellValue>;
  contextRowIds?: string[];
}

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
  columns?: string[];
  schemaProfileId: string;
  ruleVersion: string;
  validationStatus: "completed";
  validationRunId: string;
  sourceSha256: string;
  summary: ValidationSummary;
}

export interface Report {
  id: string;
  name: string;
  period: string;
  versions: Version[];
  submittedVersionId?: string;
  canSubmit: boolean;
}

export interface BackendHealth {
  status: "ok";
  schemaProfileId: string;
  ruleVersion: string;
  ai?: {
    configured: boolean;
    model: string;
    knowledgeBase: boolean;
  };
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
      value: CellValue;
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
  rate: number | null;
}

export interface AIEvaluation {
  schemaVersion: number;
  model: string;
  generatedAt: string;
  dataset: {
    description: string;
    product: string;
    rules: string;
    cases: number;
    violations: number;
  };
  runs: Array<{
    seed: number;
    cases: number;
    policies: number;
    violations: number;
    model: string;
    elapsedSeconds: number;
    handledCorrectly: EvaluationMetric;
  }>;
  metrics: {
    handledCorrectly: EvaluationMetric;
    restoredWhenInferable: EvaluationMetric;
    heldBackWhenNotInferable: EvaluationMetric;
    citedRule: EvaluationMetric;
    aiExplanationUsed: EvaluationMetric;
    numberGuardBlocked: EvaluationMetric;
    llmErrors: EvaluationMetric;
  };
  outcomes: {
    inferable: Record<string, number>;
    unknowable: Record<string, number>;
    otherRows: Record<string, number>;
    rejectedByRevalidation: number;
  };
  byRule: Array<{
    ruleId: string;
    violations: number;
    handledCorrectly: EvaluationMetric;
    restoredWhenInferable: EvaluationMetric;
    heldBackWhenNotInferable: EvaluationMetric;
    citedRule: EvaluationMetric;
    numberGuardBlocked: number;
  }>;
}
