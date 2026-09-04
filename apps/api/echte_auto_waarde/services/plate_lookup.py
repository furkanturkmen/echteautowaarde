"""Plate lookup with optional register enrichment.

The flow is local-first. A plate is normalized, the local dataset is consulted,
and only then — when something is still missing and enrichment is switched on —
is the open vehicle register asked. The register describes the car; it never
supplies mileage, trim, transmission, options or any price, so a lookup usually
ends with the user completing a few fields rather than with a finished vehicle.

Every failure mode ends in a usable outcome. Enrichment off, no network, a
timeout, an unknown plate, a truck, a malformed body: each returns a result the
interface can act on, and the manual route stays open in all of them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawVehicle, VehicleSourceUnavailable
from echte_auto_waarde.data_sources.rdw import RDW_SOURCE_KEY
from echte_auto_waarde.domain import normalization
from echte_auto_waarde.models.enums import BodyType, DataSourceType, Drivetrain, FuelType
from echte_auto_waarde.models.enums import Transmission as TransmissionEnum
from echte_auto_waarde.models.listing import DataSource
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services import vehicles as vehicle_service

logger = logging.getLogger(__name__)

# What a valuation needs and the register cannot provide. Mileage carries the
# largest adjustment in the engine, so it is never guessed.
REQUIRED_FOR_VALUATION = ("mileage_km", "transmission", "trim")


class PlateLookupStatus(StrEnum):
    """How a lookup ended."""

    LOCAL = "LOCAL"  # known locally; no external call was made
    ENRICHED = "ENRICHED"  # specifications came from the register
    NOT_FOUND = "NOT_FOUND"  # no passenger car found for this plate
    UNAVAILABLE = "UNAVAILABLE"  # register off, unreachable, slow or unusable


@dataclass
class PlateLookupResult:
    status: PlateLookupStatus
    plate: str
    vehicle: Vehicle | None = None
    draft: RawVehicle | None = None
    # Fields a valuation needs that are still empty, in domain terms.
    missing_fields: list[str] = field(default_factory=list)
    # Fields enrichment actually filled, for provenance and for the report.
    enriched_fields: list[str] = field(default_factory=list)

    @property
    def source_key(self) -> str | None:
        if self.status is PlateLookupStatus.ENRICHED:
            return RDW_SOURCE_KEY
        if self.status is PlateLookupStatus.LOCAL:
            return "local"
        return None


def ensure_register_data_source(session: Session) -> DataSource:
    """The provenance row for register-sourced specifications.

    It exists so an enriched vehicle can be traced to where its specifications
    came from. It never carries listings: the register publishes no asking
    prices, so it can contribute nothing to a market comparison.
    """
    data_source = session.scalar(select(DataSource).where(DataSource.key == RDW_SOURCE_KEY))
    if data_source is None:
        data_source = DataSource(
            key=RDW_SOURCE_KEY,
            source_type=DataSourceType.RDW,
            name="Kentekenregister (open data)",
            # Registration facts are authoritative, but this quality figure only
            # ever weighs listings in the confidence model, and this source has
            # none. It is recorded for completeness.
            quality=0.95,
        )
        session.add(data_source)
        session.flush()
    return data_source


def missing_for_valuation(vehicle: Vehicle) -> list[str]:
    """Which valuation-critical fields are still empty on a vehicle."""
    missing: list[str] = []
    if vehicle.mileage_km is None:
        missing.append("mileage_km")
    if vehicle.transmission is TransmissionEnum.UNKNOWN:
        missing.append("transmission")
    if not vehicle.trim:
        missing.append("trim")
    return missing


def _missing_on_draft(raw: RawVehicle) -> list[str]:
    missing = list(REQUIRED_FOR_VALUATION)
    if raw.mileage_km is not None:
        missing.remove("mileage_km")
    if raw.transmission:
        missing.remove("transmission")
    if raw.trim:
        missing.remove("trim")
    return missing


# The unknown members of the domain enums are gaps: they mean "we were never
# told", which is exactly what enrichment is for.
_UNKNOWN_VALUES = frozenset(
    {
        BodyType.UNKNOWN,
        FuelType.UNKNOWN,
        TransmissionEnum.UNKNOWN,
        Drivetrain.UNKNOWN,
    }
)


def _is_gap(current: object) -> bool:
    """Whether a stored value counts as absent.

    The enum check comes first on purpose: the domain enums are `StrEnum`, so an
    `isinstance(current, str)` branch would catch `BodyType.UNKNOWN` and call a
    known gap a filled value.
    """
    if current is None:
        return True
    if isinstance(current, Enum):
        return current in _UNKNOWN_VALUES
    if isinstance(current, str):
        return not current.strip()
    return False


def apply_enrichment(vehicle: Vehicle, raw: RawVehicle) -> list[str]:
    """Fill gaps on a stored vehicle from register specifications.

    Precedence is one rule: **fill gaps only, never overwrite.**

    - A value already on the vehicle wins, whoever entered it. What the user
      typed is what the user meant, and the register knows nothing about the
      individual car's condition, equipment or history.
    - An absent register value never erases a stored one, so a lookup can only
      ever add information.
    - Trim, options and mileage are never touched: the register does not publish
      them, so there is nothing authoritative to overwrite them with.

    Returns the names of the fields that were filled.
    """
    filled: list[str] = []

    def fill(attribute: str, value: object) -> None:
        if value in (None, "") or not _is_gap(getattr(vehicle, attribute)):
            return
        setattr(vehicle, attribute, value)
        filled.append(attribute)

    make = normalization.normalize_make(raw.make) if raw.make else None
    fill("make", make)
    if make and raw.model:
        fill("model", normalization.normalize_model(make, raw.model))

    if raw.body_type:
        fill("body_type", normalization.normalize_body_type(raw.body_type))
    if raw.fuel_type:
        fill("fuel_type", normalization.normalize_fuel_type(raw.fuel_type))

    fill("year", raw.year)
    fill("first_registration_date", raw.first_registration_date)
    fill("engine_displacement_cc", raw.engine_displacement_cc)
    fill("power_kw", raw.power_kw)
    fill("power_hp", raw.power_hp)
    fill("doors", raw.doors)
    fill("seats", raw.seats)
    fill("color", raw.color)
    fill("catalog_price_cents", raw.catalog_price_cents)

    return filled


def lookup_plate(
    session: Session,
    plate: str,
    source=None,
) -> PlateLookupResult:
    """Resolve a plate locally, enriching from the register where it helps.

    A stored vehicle is only enriched when something a valuation needs is
    actually missing, so a complete local vehicle costs no request at all.

    Demonstration vehicles are invisible here whatever their plate says. With
    enrichment on, a collision is simply overtaken by the register; with it off,
    the answer is that we could not look the plate up — never the fictional car.
    Demo vehicles stay reachable by id, through the examples the interface
    offers.
    """
    normalized = normalization.normalize_license_plate(plate)
    if not normalized:
        return PlateLookupResult(status=PlateLookupStatus.NOT_FOUND, plate="")

    # Demo data never answers "which car is this plate?". A synthetic vehicle
    # sharing a plate with a real one is a coincidence of invented data, so it
    # is passed over here and the register is asked instead.
    vehicle = vehicle_service.find_real_by_license_plate(session, normalized)

    if vehicle is not None:
        gaps = _specification_gaps(vehicle)
        if not gaps or source is None:
            return PlateLookupResult(
                status=PlateLookupStatus.LOCAL,
                plate=normalized,
                vehicle=vehicle,
                missing_fields=missing_for_valuation(vehicle),
            )

        raw = _fetch(source, normalized)
        if raw is None:
            # Enrichment failed or found nothing; the stored vehicle is still
            # perfectly usable, so this is not an error.
            return PlateLookupResult(
                status=PlateLookupStatus.LOCAL,
                plate=normalized,
                vehicle=vehicle,
                missing_fields=missing_for_valuation(vehicle),
            )

        filled = apply_enrichment(vehicle, raw)
        if filled:
            ensure_register_data_source(session)
            session.flush()
        return PlateLookupResult(
            status=PlateLookupStatus.LOCAL,
            plate=normalized,
            vehicle=vehicle,
            missing_fields=missing_for_valuation(vehicle),
            enriched_fields=filled,
        )

    if source is None:
        # Enrichment is switched off, or there is nothing to ask. Either way the
        # plate cannot be verified, and a demo collision must not fill the gap.
        return PlateLookupResult(status=PlateLookupStatus.UNAVAILABLE, plate=normalized)

    try:
        raw = source.fetch_vehicle(normalized)
    except VehicleSourceUnavailable as error:
        logger.info("Plate enrichment unavailable for %s: %s", normalized, error)
        return PlateLookupResult(status=PlateLookupStatus.UNAVAILABLE, plate=normalized)

    if raw is None:
        return PlateLookupResult(status=PlateLookupStatus.NOT_FOUND, plate=normalized)

    # Not stored: a lookup is a question, not a decision. The vehicle is created
    # when the user submits the completed form, so browsing plates never leaves
    # half-finished rows behind.
    return PlateLookupResult(
        status=PlateLookupStatus.ENRICHED,
        plate=normalized,
        draft=raw,
        missing_fields=_missing_on_draft(raw),
        enriched_fields=_populated_fields(raw),
    )


def _specification_gaps(vehicle: Vehicle) -> list[str]:
    """Specification fields enrichment could still fill on a stored vehicle."""
    candidates = {
        "year": vehicle.year,
        "body_type": vehicle.body_type,
        "fuel_type": vehicle.fuel_type,
        "power_hp": vehicle.power_hp,
        "engine_displacement_cc": vehicle.engine_displacement_cc,
        "first_registration_date": vehicle.first_registration_date,
        "doors": vehicle.doors,
        "seats": vehicle.seats,
        "color": vehicle.color,
        "catalog_price_cents": vehicle.catalog_price_cents,
    }
    return [name for name, value in candidates.items() if _is_gap(value)]


def _fetch(source, plate: str) -> RawVehicle | None:
    try:
        return source.fetch_vehicle(plate)
    except VehicleSourceUnavailable as error:
        logger.info("Plate enrichment unavailable for %s: %s", plate, error)
        return None


def _populated_fields(raw: RawVehicle) -> list[str]:
    return [
        name
        for name in (
            "make",
            "model",
            "year",
            "first_registration_date",
            "body_type",
            "fuel_type",
            "engine_displacement_cc",
            "power_kw",
            "power_hp",
            "doors",
            "seats",
            "color",
            "catalog_price_cents",
        )
        if getattr(raw, name) not in (None, "")
    ]
