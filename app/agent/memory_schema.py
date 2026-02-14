from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillSet(BaseModel):
    """Categorized skills extracted from a CV."""

    primary: list[str] = Field(default_factory=list, description="Core skills the user specializes in")
    secondary: list[str] = Field(default_factory=list, description="Skills mentioned but not dominant")
    tools: list[str] = Field(default_factory=list, description="Tools and platforms (e.g., Docker, AWS)")


class Experience(BaseModel):
    """A single work experience entry from a CV."""

    company: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title held")
    duration: str = Field(..., description="Duration, e.g. '2 years' or '2022-2024'")
    highlights: str = Field(..., description="1-2 sentence summary of key responsibilities/achievements")


class CVSummary(BaseModel):
    """Structured summary of a CV. Facts only — no user intentions."""

    professional_summary: str = Field(..., description="AI-generated 2-3 sentence professional overview")
    seniority_level: str = Field(..., description="Junior / Mid / Senior / Lead / Principal")
    years_of_experience: int = Field(..., description="Total years of professional experience")
    primary_domain: str = Field(..., description="Primary domain, e.g. Backend, Frontend, Data, DevOps")
    skills: SkillSet = Field(default_factory=SkillSet)
    experience: list[Experience] = Field(default_factory=list, description="Last 3-5 roles, condensed")
    education: list[str] = Field(default_factory=list, description="Degrees and certifications")


class UserProfile(BaseModel):
    """
    Core identity of the user. Only contains explicit facts.
    """

    id: int = 1
    name: str | None = None
    role: str | None = Field(default=None, description="Current job title, e.g. 'Senior Backend Engineer'")
    cv_summary: CVSummary | None = Field(default=None, description="Structured CV summary")
    cv_uploaded: bool = Field(default=False, description="Whether a CV has been uploaded")


class Preference(BaseModel):
    """
    A specific constraint or preference for job searching.
    """

    key: str = Field(..., description="The setting name, e.g. 'min_salary', 'remote', 'tech_stack'")
    value: Any = Field(..., description="The value. Can be string, int, list, or boolean.")
    category: Literal["hard", "soft"] = Field(
        "soft", description="'hard' for strict filters (must have), 'soft' for preferences (nice to have)"
    )
