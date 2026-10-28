"""Public contracts compatible with the initial frontend's bounded integer demo."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SAFE_INTEGER = 9_007_199_254_740_991


class DataRow(BaseModel):
    id: str
    product: str
    previous: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    opening: int = Field(ge=0, le=MAX_SAFE_INTEGER)


class Issue(BaseModel):
    id: str
    ruleId: Literal["R-01", "R-07"]
    rowId: str
    field: Literal["opening", "product"]
    title: str
    actual: str | int
    expected: int | None = None
    repeated: bool


class ValidationSummary(BaseModel):
    totalChecks: int
    passedChecks: int
    failedChecks: int
    notEvaluatedChecks: int


class Version(BaseModel):
    id: str
    number: int
    filename: str
    createdAt: str
    rows: list[DataRow]
    issues: list[Issue]
    schemaProfileId: Literal["demo_csv_v1"]
    ruleVersion: Literal["demo_rules_v1"]
    validationStatus: Literal["completed"]
    validationRunId: str
    sourceSha256: str
    summary: ValidationSummary


class Report(BaseModel):
    id: str
    name: str
    period: str
    versions: list[Version]
    submittedVersionId: str | None = None
    canSubmit: bool


class Suggestion(BaseModel):
    explanation: str
    verification: Literal["unavailable"] = "unavailable"
    source: Literal["demo"] = "demo"


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    versionId: str = Field(min_length=1)
