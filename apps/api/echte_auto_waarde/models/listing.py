"""Listing, seller, data-source and snapshot entities.

A Listing is a market offering of a Vehicle. Every observation of that listing
is appended as a ListingSnapshot; existing snapshots are never rewritten, which
is what eventually makes days-on-market, price reductions and relisting
behaviour derivable from real observations.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echte_auto_waarde.db.base import Base, TimestampMixin
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus, SellerType

if TYPE_CHECKING:
    from echte_auto_waarde.models.vehicle import Vehicle


class DataSource(Base, TimestampMixin):
    """Where a listing came from. One row per configured adapter."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType, native_enum=False, length=16)
    )
    name: Mapped[str] = mapped_column(String(96))

    # Quality in 0..1, used as one input to the confidence model. Synthetic data
    # scores low on purpose: it validates methodology, not market accuracy.
    quality: Mapped[float] = mapped_column(default=0.5)

    listings: Mapped[list[Listing]] = relationship(back_populates="data_source")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DataSource {self.key}>"


class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_type: Mapped[SellerType] = mapped_column(
        Enum(SellerType, native_enum=False, length=16), default=SellerType.UNKNOWN
    )
    name: Mapped[str | None] = mapped_column(String(96))
    city: Mapped[str | None] = mapped_column(String(64))

    listings: Mapped[list[Listing]] = relationship(back_populates="seller")


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id", ondelete="SET NULL"))
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)

    # Identifier used by the originating source; unique within that source.
    external_reference: Mapped[str] = mapped_column(String(96), index=True)

    asking_price_cents: Mapped[int] = mapped_column(Integer, index=True)
    url: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, native_enum=False, length=16), default=ListingStatus.ACTIVE
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    vehicle: Mapped[Vehicle] = relationship(back_populates="listings")
    seller: Mapped[Seller | None] = relationship(back_populates="listings")
    data_source: Mapped[DataSource] = relationship(back_populates="listings")
    snapshots: Mapped[list[ListingSnapshot]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="ListingSnapshot.observed_at",
    )

    __table_args__ = (
        Index("ix_listings_source_reference", "data_source_id", "external_reference", unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Listing {self.id} vehicle={self.vehicle_id} {self.asking_price_cents}c>"


class ListingSnapshot(Base):
    """One observation of a listing at a point in time.

    Append-only: a price change adds a snapshot rather than editing history.
    """

    __tablename__ = "listing_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    asking_price_cents: Mapped[int] = mapped_column(Integer)
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, native_enum=False, length=16), default=ListingStatus.ACTIVE
    )
    raw_metadata: Mapped[str | None] = mapped_column(Text)

    listing: Mapped[Listing] = relationship(back_populates="snapshots")
