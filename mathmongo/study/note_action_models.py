"""Bounded note lifecycle requests; never accept database names or filesystem paths."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


class NoteActionRequest(BaseModel):
    """One exact revision and persisted attempt, with explicit copy title if applicable."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["duplicate", "delete"]
    request_id: UUID
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    title: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def action_fields(self):
        """A copy has a title; deleting cannot smuggle metadata edits."""
        if self.action == "duplicate" and not self.title.strip():
            raise ValueError("Escribe el título de la copia.")
        if self.action == "delete" and self.title:
            raise ValueError("La eliminación no modifica metadatos.")
        return self
