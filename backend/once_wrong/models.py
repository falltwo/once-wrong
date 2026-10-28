"""Public contracts for the demo and text-preserving life underwriting profiles."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from once_wrong_ai.ai_review.api import IssueResponse, SuggestionResponse

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


class VersionBase(BaseModel):
    id: str
    number: int
    filename: str
    createdAt: str
    validationStatus: Literal["completed"]
    validationRunId: str
    sourceSha256: str
    summary: ValidationSummary


class DemoVersion(VersionBase):
    rows: list[DataRow]
    issues: list[Issue]
    schemaProfileId: Literal["demo_csv_v1"]
    ruleVersion: Literal["demo_rules_v1"]


class LifeDataRow(BaseModel):
    id: str
    row: int = Field(ge=1)
    values: dict[str, str]


class LifeVersion(VersionBase):
    rows: list[LifeDataRow]
    issues: list[IssueResponse]
    columns: list[str]
    schemaProfileId: Literal["life_underwriting_v1"]
    ruleVersion: Literal["life_field_rules_v1"]


Version = Annotated[DemoVersion | LifeVersion, Field(discriminator="schemaProfileId")]


class Report(BaseModel):
    id: str
    name: str
    period: str
    versions: list[Version]
    submittedVersionId: str | None = None
    canSubmit: bool


Suggestion = SuggestionResponse


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    versionId: str = Field(min_length=1)
