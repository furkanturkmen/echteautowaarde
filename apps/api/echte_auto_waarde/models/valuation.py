"""Stored valuation results.

A valuation is a snapshot of what the engine concluded at one moment, including
the evidence it used. Storing the algorithm version keeps results produced by
different methodology versions comparable later.

Structured detail (adjustments, confidence factors, similarity reasons) is kept
in JSON columns: it is read as a whole, never queried field by field, and the
JSON type is supported by both SQLite and other relational databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echte_auto_waarde.db.base import Base, TimestampMixin
from echte_auto_waarde.domain.deals import DealClassification

if TYPE_CHECKING:
    from echte_auto_waarde.models.listing import Listing
    from echte_auto_waarde.models.vehicle import Vehicle


class Valuation(Base, TimestampMixin):
    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )

    # The seller's asking price, when the user supplied one. Never mixed up with
    # the estimated market value or the recommended purchase range.
    asking_price_cents: Mapped[int | None] = mapped_column(Integer)

    estimated_market_value_cents: Mapped[int] = mapped_column(Integer)
    # The weighted market price before adjustments. Stored because without it a
    # retrieved valuation cannot show how it reached its estimate. Nullable only
    # because valuations created before this column existed do not have one.
    market_basis_cents: Mapped[int | None] = mapped_column(Integer)
    recommended_buy_price_low_cents: Mapped[int] = mapped_column(Integer)
    recommended_buy_price_high_cents: Mapped[int] = mapped_column(Integer)

    deal_classification: Mapped[DealClassification | None] = mapped_column(
        Enum(DealClassification, native_enum=False, length=24)
    )

    confidence_score: Mapped[float] = mapped_column(Float)
    comparable_count: Mapped[int] = mapped_column(Integer)
    widening_level: Mapped[int] = mapped_column(Integer, default=0)

    market_statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    adjustments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    algorithm_version: Mapped[str] = mapped_column(String(32))

    target_vehicle: Mapped[Vehicle] = relationship()
    comparables: Mapped[list[ComparableResultRecord]] = relationship(
        back_populates="valuation",
        cascade="all, delete-orphan",
        order_by="ComparableResultRecord.similarity_score.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Valuation {self.id} vehicle={self.target_vehicle_id}>"


class ComparableResultRecord(Base):
    """Why one listing was used as evidence for a valuation."""

    __tablename__ = "valuation_comparables"

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_id: Mapped[int] = mapped_column(
        ForeignKey("valuations.id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))

    similarity_score: Mapped[float] = mapped_column(Float)
    # Contribution to the weighted market basis, in EUR cents.
    adjusted_price_cents: Mapped[int | None] = mapped_column(Integer)
    weight: Mapped[float | None] = mapped_column(Float)

    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    differences: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    valuation: Mapped[Valuation] = relationship(back_populates="comparables")
    listing: Mapped[Listing] = relationship()
