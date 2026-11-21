"""Validated presentation state in existing knowledge_graph_maps documents."""

from __future__ import annotations

import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator


class StudyGoal(BaseModel):
    """An explicit study marker, never a published empty concept."""

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)
    id: str = Field(max_length=100)
    label: str = Field(min_length=1, max_length=250)
    point: list[float] = Field(min_length=3, max_length=3)
    state: Literal["pending", "working", "reviewed"] = "pending"
    draft_id: str = Field(default="", max_length=100, alias="draftId")
    concept_key: str = Field(default="", max_length=1000, alias="conceptKey")

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        """Reject arbitrary marker paths or operator-shaped identifiers."""
        UUID(value)
        return value


class StudyView(BaseModel):
    """Versioned view data; positions and goals do not change concept semantics."""

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)
    version: Literal[1] = 1
    points: dict[str, list[float]] = Field(default_factory=dict, max_length=10000)
    flat_points: dict[str, list[float]] = Field(
        default_factory=dict, max_length=10000, alias="flatPoints"
    )
    pinned: list[str] = Field(default_factory=list, max_length=10000)
    areas: list[str] = Field(default_factory=list, max_length=6)
    mandala: bool = False
    goals: list[StudyGoal] = Field(default_factory=list, max_length=1000)
    members: list[str] | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def finite_geometry(self):
        """Keep the saved sphere on S² and reject oversized/nonfinite coordinates."""
        for key, point in self.points.items():
            if (
                not key
                or len(key) > 1000
                or len(point) != 3
                or not all(math.isfinite(v) for v in point)
                or abs(math.hypot(*point) - 1) > 1e-5
            ):
                raise ValueError("Invalid spherical position")
        for key, point in self.flat_points.items():
            if (
                len(key) > 1000
                or len(point) != 2
                or not all(math.isfinite(v) and abs(v) <= 5 for v in point)
            ):
                raise ValueError("Invalid planar position")
        for goal in self.goals:
            if (
                not all(math.isfinite(v) for v in goal.point)
                or abs(math.hypot(*goal.point) - 1) > 1e-5
            ):
                raise ValueError("Invalid goal position")
        if len({g.id for g in self.goals}) != len(self.goals) or any(
            len(area) > 200 for area in self.areas
        ):
            raise ValueError("Invalid goals or areas")
        if self.members is not None and (
            len(set(self.members)) != len(self.members)
            or any(not key or len(key) > 1000 for key in self.members)
        ):
            raise ValueError("Invalid view membership")
        return self


class RoomSphere(BaseModel):
    """A saved-view reference and its room pose, independent of node geometry."""

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)
    view_uid: str
    position: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def valid_pose(self):
        """Use bounded room coordinates and stable saved-view identities."""
        UUID(self.view_uid)
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in self.position):
            raise ValueError("Invalid room pose")
        return self


class StudyRoom(BaseModel):
    """Only presentation and canonical resource references belong to a room."""

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    spheres: list[RoomSphere] = Field(default_factory=list, max_length=100)
    document_id: str = Field(default="", max_length=100)
    note_id: str = Field(default="", max_length=100)
    goal_view_uid: str = Field(default="", max_length=100)
    goal_id: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def unique_views(self):
        """Reject duplicate sphere references without capping the room at two."""
        if len({sphere.view_uid for sphere in self.spheres}) != len(self.spheres):
            raise ValueError("A saved view can occur only once per room")
        return self
