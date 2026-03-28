from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Bucket(str, Enum):
    safe = "safe"
    target = "target"
    reach = "reach"


class Profile(BaseModel):
    full_name: str = Field(default="Demo Student")
    nationality: str = Field(default="Bangladesh")
    target_country: str = Field(default="South Korea")
    degree_level: Literal["bachelor", "master", "phd"] = "master"
    major: str = Field(default="Computer Science")
    # Raw CGPA on the student's transcript; see gpa_scale_max for "out of".
    gpa: float = Field(default=3.2, ge=0, le=10.0)
    gpa_scale_max: float = Field(default=4.0, ge=1.0, le=10.0)
    has_ielts: bool = False
    budget_usd: int = Field(default=0, ge=0)
    interests: list[str] = Field(default_factory=lambda: ["multi-agent systems"])

    # Sources (Profile Agent ingest)
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_urls: list[str] = Field(default_factory=list)
    resume_text: str | None = None

    # Enriched (from GitHub, resume, portfolio pages)
    languages: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    consistency_summary: str | None = None

    # Ingest diagnostics (non-secret)
    ingest_meta: dict[str, Any] = Field(default_factory=dict)

    # Extra form fields (wizard)
    academic_status: str | None = None
    ielts_score: float | None = None

    def gpa_as_us_four_point(self) -> float:
        """Map declared CGPA to ~4.0 US-style scale for minimum_GPA comparisons.

        If CGPA is slightly above the chosen max (e.g. 4.11 on a nominally /4.0 scale —
        weighted courses, A+, or transcript quirks), the effective denominator is raised
        so the ratio caps at a 4.0 US-style equivalent instead of rejecting the profile.
        """
        scale = self.gpa_scale_max if self.gpa_scale_max > 0 else 4.0
        denom = max(scale, self.gpa, 1e-9)
        return max(0.0, min(4.0, (self.gpa / denom) * 4.0))


class ProfileGaps(BaseModel):
    missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Opportunity(BaseModel):
    title: str
    country: str | None = None
    url: str | None = None
    deadline: date | None = None
    fully_funded: bool | None = None
    requires_ielts: bool | None = None
    minimum_gpa: float | None = None
    estimated_fees_usd: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    fit: float = Field(ge=0, le=1)
    eligibility: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    funding: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class ScoredOpportunity(BaseModel):
    opportunity: Opportunity
    total_score: float = Field(ge=0, le=1)
    bucket: Bucket
    breakdown: ScoreBreakdown
    reasons: list[str] = Field(default_factory=list)


class CriticDecision(BaseModel):
    action: Literal["pass", "warn", "block"]
    reason: str
    affected_title: str | None = None


class ExecutionPlan(BaseModel):
    days: list[str]


class DraftOutputs(BaseModel):
    professor_email_subject: str
    professor_email_body: str
    sop_outline: list[str]


class FollowUpItem(BaseModel):
    due_in_days: int = Field(ge=1, le=30)
    channel: Literal["email"] = "email"
    message: str


class ApplySmartState(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    profile: Profile | None = None
    gaps: ProfileGaps | None = None
    opportunities: list[Opportunity] = Field(default_factory=list)
    scored: list[ScoredOpportunity] = Field(default_factory=list)
    critic: CriticDecision | None = None
    plan: ExecutionPlan | None = None
    drafts: DraftOutputs | None = None
    followups: list[FollowUpItem] = Field(default_factory=list)

