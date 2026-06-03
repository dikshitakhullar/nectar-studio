"""SQLAlchemy 2.0 ORM models for the FastAPI service.

Three tables:

* ``projects``     — one row per uploaded DWG bundle.
* ``rooms``        — one row per parsed room; stores the parsed-IR blob and
                     the in-progress ConfirmedRoom delta as JSON columns.
* ``jobs``         — one row per /generate request; tracks status + result.

Audit columns (``created_at`` / ``updated_at``) are populated by SQLAlchemy
defaults so they show up in any logs the studio surfaces.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, Text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared declarative base."""


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Untitled project")
    location: Mapped[str] = mapped_column(String, nullable=False, default="delhi")
    # Local filesystem paths to the uploaded DWG/DXF files (may be empty if
    # uploaded blobs were inline). Stored as strings, not foreign keys.
    ceiling_path: Mapped[str | None] = mapped_column(String, nullable=True)
    furniture_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # Raw parsed Project IR (model_dump from
    # ``lighting_engine.models.geometry.Project``). Useful for debugging.
    parsed_ir: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
    )

    rooms: Mapped[list["RoomRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )


class RoomRecord(Base):
    __tablename__ = "rooms"

    # Composite primary key: a parser-derived slug like "drawing-room-00" is
    # only unique within ONE project — across projects, two designers' Delhi
    # houses can both have a "drawing-room-00". The composite key lets the
    # API give every project its own id namespace without re-slugifying.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True, index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # JSON blob: ConfirmedRoom (parsed-IR view + any clarification deltas).
    confirmed_room: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False, default="first_class")
    status: Mapped[str] = mapped_column(String, nullable=False, default="new")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
    )

    project: Mapped[Project] = relationship(back_populates="rooms")
    jobs: Mapped[list["Job"]] = relationship(back_populates="room")


class Job(Base):
    __tablename__ = "jobs"
    # Composite FK back to (rooms.project_id, rooms.id) since rooms now has a
    # composite PK. Project_id is kept as its own simple FK to projects too
    # so deletes cascade cleanly.
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "room_id"],
            ["rooms.project_id", "rooms.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    room_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full PlanResponse blob once status == "done".
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
    )

    project: Mapped[Project] = relationship(back_populates="jobs")
    # The room relationship shares project_id with the project relationship
    # (composite FK on rooms (project_id, id)); declare the overlap so
    # SQLAlchemy knows it's intentional rather than a misconfiguration.
    room: Mapped[RoomRecord] = relationship(
        back_populates="jobs", overlaps="jobs,project",
    )
