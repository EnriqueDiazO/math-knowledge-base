"""Explicit Cuaderno contracts matching the historical collections, not arbitrary Mongo forms."""

from datetime import date
from typing import Annotated
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

Text = Annotated[str, Field(max_length=2000)]
Required = Annotated[str, Field(min_length=1, max_length=500)]


class ActivityFields(BaseModel):
    """Validate user fields without accepting server identities or association rewrites."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def trim_strings(cls, value):
        """Task metadata follows the existing trimmed forms; document LaTeX is elsewhere."""
        return value.strip() if isinstance(value, str) else value


class WorklogFields(ActivityFields):
    """A dated time block with evidence and its next step."""

    date: date
    block: Literal["AM", "PM", "Noche"] = "AM"
    hours: float = Field(default=0, ge=0, le=100000)
    status: Literal["Planificado", "En progreso", "Hecho", "Bloqueado", "Cancelado"] = "Planificado"
    project: Required
    task: Required
    module: Text = ""
    description_evidence: Text = ""
    evidence_url: Text = ""
    next_step: Text = ""
    tags: list[Required] = Field(default_factory=list, max_length=100)


class BacklogFields(ActivityFields):
    """Planning metadata shared with the historical Kanban."""

    project: Required
    task: Required
    owner: Required
    module: Text = ""
    description: Text = ""
    priority: Literal["Alta", "Media", "Baja"] = "Media"
    status: Literal["Todo", "Doing", "Done", "Blocked", "Canceled"] = "Todo"
    estimate_hours: float | None = Field(default=None, ge=0, le=100000)
    target_date: date | None = None
    tags: list[Required] = Field(default_factory=list, max_length=100)


class DeliverableFields(ActivityFields):
    """Keep links as metadata; never interpret a supplied path as server file access."""

    date: date
    project: Required
    deliverable: Required
    type: Literal["reporte", "codigo", "dataset", "presentacion", "evidencia", "otro"] = "reporte"
    url_or_path: Required
    notes: Text = ""
    commit_ref: Text = ""
    tags: list[Required] = Field(default_factory=list, max_length=100)


class WeeklyFields(ActivityFields):
    """ISO week, four ordered reflections and explicit optional metric overrides."""

    iso_year: int = Field(ge=1900, le=9998)
    iso_week: int = Field(ge=1, le=53)
    weekly_objectives: list[Text] = Field(default_factory=list, max_length=100)
    wins: list[Text] = Field(default_factory=list, max_length=100)
    blocks_risks: list[Text] = Field(default_factory=list, max_length=100)
    plan_next_week: list[Text] = Field(default_factory=list, max_length=100)
    manual_override_metrics: bool = False
    manual_real_hours: float | None = Field(default=None, ge=0, le=100000)
    manual_tasks_done: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_week(self):
        """Reject a nonexistent ISO week rather than silently moving the review."""
        date.fromisocalendar(self.iso_year, self.iso_week, 1)
        if self.manual_override_metrics and (
            self.manual_real_hours is None or self.manual_tasks_done is None
        ):
            raise ValueError("Indica las dos métricas manuales o desactiva la sustitución.")
        return self


MODELS = {
    "worklog": WorklogFields,
    "backlog": BacklogFields,
    "deliverables": DeliverableFields,
    "weekly": WeeklyFields,
}
Kind = Literal["worklog", "backlog", "deliverables", "weekly"]


class ActivityWrite(BaseModel):
    """Creation replay identity or the complete revision observed before an edit."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    revision: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    fields: dict
