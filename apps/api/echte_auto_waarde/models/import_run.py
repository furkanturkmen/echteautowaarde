"""A record of one market import.

Exists for two reasons. It makes an import auditable — what was loaded, from
where, when, and whether it worked. And it is what makes the removal rule safe:
only a run that reached COMPLETED may conclude anything from a listing's
absence, so a crash or a rejected file can never empty a market.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echte_auto_waarde.db.base import Base
from echte_auto_waarde.models.enums import ImportMode, ImportRunStatus
from echte_auto_waarde.models.listing import DataSource


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)

    # What this file claimed to describe, for example "bmw-3-serie-2026-w09".
    # A full snapshot may only draw conclusions within its own scope.
    scope: Mapped[str] = mapped_column(String(96), index=True)
    mode: Mapped[ImportMode] = mapped_column(
        Enum(ImportMode, native_enum=False, length=16), default=ImportMode.INCREMENTAL
    )
    status: Mapped[ImportRunStatus] = mapped_column(
        Enum(ImportRunStatus, native_enum=False, length=16), default=ImportRunStatus.STARTED
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_file: Mapped[str | None] = mapped_column(String(512))
    listings_seen: Mapped[int] = mapped_column(Integer, default=0)
    listings_created: Mapped[int] = mapped_column(Integer, default=0)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0)
    # Only ever non-zero for a completed full snapshot.
    listings_removed: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    data_source: Mapped[DataSource] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ImportRun {self.id} {self.mode} {self.status} scope={self.scope!r}>"
