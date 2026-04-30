from typing import Any

from pydantic import BaseModel, Field


class RepoInput(BaseModel):
    url: str = Field(..., description="GitHub repository URL")
    owner: str
    repo: str


class ProjectBasicInfo(BaseModel):
    owner: str
    repo: str
    name: str
    description: str | None = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    license: str | None = None
    readme: str | None = None


class MetricBundle(BaseModel):
    github: dict[str, Any] = Field(default_factory=dict)
    opendigger: dict[str, Any] = Field(default_factory=dict)
    missing_metrics: list[str] = Field(default_factory=list)


class SelectedMetric(BaseModel):
    name: str
    value: Any = None
    source: str
    reason: str


class RetrievedDoc(BaseModel):
    title: str
    content: str
    source: str


class EvaluationReport(BaseModel):
    repo: str
    project_type: str
    overall_score: int
    dimension_scores: dict[str, int] = Field(default_factory=dict)
    summary: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)


class QualityResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class EvaluationState(BaseModel):
    input_url: str
    owner: str | None = None
    repo: str | None = None
    basic_info: ProjectBasicInfo | None = None
    project_type: str | None = None
    raw_metrics: MetricBundle | None = None
    selected_metrics: list[SelectedMetric] = Field(default_factory=list)
    retrieved_context: list[RetrievedDoc] = Field(default_factory=list)
    report: EvaluationReport | None = None
    quality_result: QualityResult | None = None
    retry_count: int = 0
    errors: list[str] = Field(default_factory=list)
