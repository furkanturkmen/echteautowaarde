"""Data-source adapter interface.

Every source of market or vehicle data enters the application through an adapter
that yields these raw records. The domain and valuation engines depend on this
interface only, never on a specific website or API, so a real market-data
adapter can be added later without touching the vehicle domain, the comparable
engine, the valuation engine, the API, the frontend or the AI layer.

Raw records hold source wording (e.g. "Automaat", "adaptieve cruise"); the
ingestion service normalizes them and keeps the raw text for traceability.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from echte_auto_waarde.models.enums import DataSourceType, ListingStatus


@dataclass(frozen=True)
class RawVehicle:
    make: str
    model: str
    year: int | None = None
    mileage_km: int | None = None
    trim: str | None = None
    generation: str | None = None
    body_type: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    drivetrain: str | None = None
    engine_description: str | None = None
    engine_displacement_cc: int | None = None
    power_kw: int | None = None
    power_hp: int | None = None
    first_registration_date: date | None = None
    license_plate: str | None = None
    color: str | None = None
    doors: int | None = None
    seats: int | None = None
    catalog_price_cents: int | None = None
    option_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawSeller:
    seller_type: str
    name: str | None = None
    city: str | None = None


@dataclass(frozen=True)
class RawSnapshot:
    observed_at: datetime
    asking_price_cents: int
    mileage_km: int | None = None
    status: ListingStatus = ListingStatus.ACTIVE


@dataclass(frozen=True)
class RawListing:
    external_reference: str
    vehicle: RawVehicle
    asking_price_cents: int
    first_seen_at: datetime
    last_seen_at: datetime
    seller: RawSeller | None = None
    url: str | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    snapshots: tuple[RawSnapshot, ...] = field(default_factory=tuple)


class DataSourceAdapter(Protocol):
    """A source of listings.

    Attributes describe the source itself; `quality` (0..1) feeds the confidence
    model, so a source that cannot claim real market accuracy scores low.
    """

    key: str
    source_type: DataSourceType
    name: str
    quality: float

    def fetch_listings(self) -> Iterable[RawListing]:
        """Yield the listings this source currently knows about."""
        ...
