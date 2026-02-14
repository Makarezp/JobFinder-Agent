from typing import Any, Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """
    Core identity of the user. Only contains explicit facts.
    """

    id: int = 1
    name: str | None = None
    role: str | None = Field(default=None, description="Current job title, e.g. 'Senior Backend Engineer'")
    cv_text: str | None = Field(default=None, description="Raw text of the CV")


class Preference(BaseModel):
    """
    A specific constraint or preference for job searching.
    """

    key: str = Field(..., description="The setting name, e.g. 'min_salary', 'remote', 'tech_stack'")
    value: Any = Field(..., description="The value. Can be string, int, list, or boolean.")
    category: Literal["hard", "soft"] = Field(
        "soft", description="'hard' for strict filters (must have), 'soft' for preferences (nice to have)"
    )
