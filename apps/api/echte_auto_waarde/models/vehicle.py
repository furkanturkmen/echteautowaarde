"""Vehicle entities.

A Vehicle is the specification identity of one physical car: what it is, how it
is equipped and how far it has driven. A Listing (see listing.py) is a market
offering of such a vehicle — the two are deliberately separate, because the same
vehicle can be observed, relisted or re-priced many times.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echte_auto_waarde.db.base import Base, TimestampMixin
from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission

if TYPE_CHECKING:
    from echte_auto_waarde.models.listing import Listing
    from echte_auto_waarde.models.option import VehicleOption


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Dutch license plate, stored without separators (e.g. "K123AB").
    license_plate: Mapped[str | None] = mapped_column(String(16), index=True)

    # Canonical identity. Raw source spellings are kept in *_raw for traceability.
    make: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    generation: Mapped[str | None] = mapped_column(String(32), index=True)
    trim: Mapped[str | None] = mapped_column(String(64), index=True)

    make_raw: Mapped[str | None] = mapped_column(String(128))
    model_raw: Mapped[str | None] = mapped_column(String(128))
    trim_raw: Mapped[str | None] = mapped_column(String(128))

    body_type: Mapped[BodyType] = mapped_column(
        Enum(BodyType, native_enum=False, length=16), default=BodyType.UNKNOWN
    )
    fuel_type: Mapped[FuelType] = mapped_column(
        Enum(FuelType, native_enum=False, length=16), default=FuelType.UNKNOWN
    )
    transmission: Mapped[Transmission] = mapped_column(
        Enum(Transmission, native_enum=False, length=16), default=Transmission.UNKNOWN
    )
    drivetrain: Mapped[Drivetrain] = mapped_column(
        Enum(Drivetrain, native_enum=False, length=8), default=Drivetrain.UNKNOWN
    )

    engine_description: Mapped[str | None] = mapped_column(String(64))
    engine_displacement_cc: Mapped[int | None] = mapped_column(Integer)
    power_kw: Mapped[int | None] = mapped_column(Integer)
    power_hp: Mapped[int | None] = mapped_column(Integer)

    year: Mapped[int | None] = mapped_column(Integer, index=True)
    first_registration_date: Mapped[date | None] = mapped_column(Date)
    mileage_km: Mapped[int | None] = mapped_column(Integer, index=True)

    color: Mapped[str | None] = mapped_column(String(32))
    doors: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int | None] = mapped_column(Integer)

    # Original list price when new, in EUR cents. Never used as a market price.
    catalog_price_cents: Mapped[int | None] = mapped_column(Integer)

    # Free-form provenance from the originating adapter, stored as JSON text.
    source_metadata: Mapped[str | None] = mapped_column(Text)

    specification: Mapped[VehicleSpecification | None] = relationship(
        back_populates="vehicle", uselist=False, cascade="all, delete-orphan"
    )
    options: Mapped[list[VehicleOption]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )
    listings: Mapped[list[Listing]] = relationship(back_populates="vehicle")

    __table_args__ = (
        # The comparable engine always filters on make + model first.
        Index("ix_vehicles_make_model_year", "make", "model", "year"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Vehicle {self.id} {self.make} {self.model} {self.year}>"


class VehicleSpecification(Base, TimestampMixin):
    """Technical attributes that do not belong on the basic vehicle entity.

    Kept separate so enrichment sources (for example RDW) can fill in detail
    without widening the entity the comparable engine works from.
    """

    __tablename__ = "vehicle_specifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), unique=True, index=True
    )

    mass_kg: Mapped[int | None] = mapped_column(Integer)
    towing_capacity_braked_kg: Mapped[int | None] = mapped_column(Integer)
    battery_capacity_kwh: Mapped[int | None] = mapped_column(Integer)
    electric_range_km: Mapped[int | None] = mapped_column(Integer)
    co2_emissions_gpkm: Mapped[int | None] = mapped_column(Integer)
    top_speed_kmh: Mapped[int | None] = mapped_column(Integer)
    apk_valid_until: Mapped[date | None] = mapped_column(Date)

    vehicle: Mapped[Vehicle] = relationship(back_populates="specification")
