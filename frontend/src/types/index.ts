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
export interface Version {
  id: string;
  number: number;
  filename: string;
  createdAt: string;
  rows: DataRow[];
  issues: Issue[];
}
export interface Report {
  id: string;
  name: string;
  period: string;
  versions: Version[];
  submittedVersionId?: string;
}
export interface Suggestion {
  explanation: string;
  value?: number;
  verification: "passed" | "unavailable";
  source: "demo";
}
