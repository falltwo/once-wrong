export type CellValue = string | number | boolean | null;
export type RepeatStatus = "new" | "repeated" | "regressed";

export interface DemoDataRow {
  id: string;
  product: string;
  previous: number;
  opening: number;
}

export interface TextDataRow {
  id: string;
  row: number;
  values: Record<string, CellValue>;
  fileId?: string;
  datasetType?: string;
}

export type DataRow = DemoDataRow | TextDataRow;

export interface IssueCell {
  row: number;
  rowId: string;
  column: string;
  value: CellValue;
  fileId?: string;
  datasetType?: string;
}

export interface Issue {
  id: string;
  ruleId: string;
  title: string;
  repeated: boolean;
  repeatStatus?: RepeatStatus;
  firstSeenNumber?: number;
  prevSeenNumber?: number | null;
  fixedInNumber?: number | null;
  issueKey?: string;
  severity?: "error" | "warning";
  /** Single-file demo fields. */
  rowId?: string;
  field?: string;
  actual?: CellValue;
  expected?: CellValue;
  /** Life profile and filing issue fields. */
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

export interface VersionFile {
  id: string;
  datasetType: string;
  filename: string;
  sourceSha256: string;
  columns: string[];
  rows: TextDataRow[];
  prototype?: unknown;
  eventDateColumn?: string;
}

export interface Version {
  id: string;
  number: number;
  filename: string;
  createdAt: string;
  rows: DataRow[];
  issues: Issue[];
  columns?: string[];
  files?: VersionFile[];
  schemaProfileId?: string;
  ruleVersion?: string;
  validationStatus?: "completed";
  validationRunId?: string;
  sourceSha256?: string;
  manifestSha256?: string;
  summary?: ValidationSummary;
  evidence?: {
    notice?: string;
    executedRuleIds?: string[];
    notEvaluated?: Array<{
      code: string;
      reason: string;
      checks: number;
      source?: string;
    }>;
  };
}

export interface Report {
  id: string;
  name: string;
  period: string;
  versions: Version[];
  submittedVersionId?: string;
  canSubmit?: boolean;
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

export interface Citation {
  id: string;
  source: string;
  section: string[];
  page?: number | null;
  /** 知識庫裡這段手冊的原文（從 PDF 抽出的文字）；後端提供時才有。 */
  excerpt?: string;
  /** AI 依據、且後端逐字核對過出現在 excerpt 裡的句子。 */
  quote?: string | null;
  /** 後端有提供原始手冊時，開到該頁的相對網址。 */
  pdfUrl?: string | null;
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
      fileId?: string;
      datasetType?: string;
    }>;
  } | null;
  rejectedSuggestions: string[];
  citations: Citation[];
  /** AI 宣稱引用、但對不上手冊原文的句子；後端提供時才有。 */
  rejectedQuotes?: string[];
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

export interface Evaluation {
  schemaVersion?: number;
  model: string;
  generatedAt?: string;
  dataset?: {
    description?: string;
    product?: string;
    rules?: string;
    cases?: number;
    violations?: number;
  };
  runs?: Array<Record<string, unknown>>;
  metrics: Record<string, EvaluationMetric>;
  byRule?: Array<{
    ruleId: string;
    violations: number;
    handledCorrectly: EvaluationMetric;
    restoredWhenInferable: EvaluationMetric;
    heldBackWhenNotInferable: EvaluationMetric;
    citedRule: EvaluationMetric;
    numberGuardBlocked: number;
  }>;
  outcomes?: Record<string, unknown>;
  evaluationContext: {
    evaluatedModel: string;
    runtimeModel: string;
    runtimeConfigured: boolean;
    modelMatchesRuntime: boolean;
    displayNotice: string;
  };
}
