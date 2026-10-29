"""Public contracts for the demo and text-preserving life underwriting profiles."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

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
    issueKey: str | None = None
    repeatStatus: Literal["new", "repeated", "regressed"] | None = None
    firstSeenNumber: int | None = None
    prevSeenNumber: int | None = None
    fixedInNumber: int | None = None


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
    fileId: str | None = None
    datasetType: str | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class LifeVersion(VersionBase):
    rows: list[LifeDataRow]
    issues: list[IssueResponse]
    columns: list[str]
    schemaProfileId: Literal["life_underwriting_v1"]
    ruleVersion: Literal["life_field_rules_v1"]


class FilingFile(BaseModel):
    id: str
    datasetType: str
    filename: str
    sourceSha256: str
    columns: list[str]
    rows: list[LifeDataRow]
    prototype: bool = True
    eventDateColumn: str | None = None


class FilingVersion(VersionBase):
    rows: list[LifeDataRow]
    issues: list[IssueResponse]
    columns: list[str]
    files: list[FilingFile]
    manifestSha256: str
    evidence: dict
    schemaProfileId: Literal["life_filing_v1"]
    ruleVersion: Literal["life_filing_rules_v1"]


Version = Annotated[
    DemoVersion | LifeVersion | FilingVersion, Field(discriminator="schemaProfileId")
]


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
