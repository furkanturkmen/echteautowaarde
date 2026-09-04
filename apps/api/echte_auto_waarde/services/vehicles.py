"""Vehicle lookup and manual entry."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from echte_auto_waarde.data_sources.base import RawVehicle
from echte_auto_waarde.domain import normalization
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.listing import DataSource
from echte_auto_waarde.models.option import VehicleOption, VehicleOptionDefinition
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.ingestion import split_option_texts, sync_option_definitions

MANUAL_SOURCE_KEY = "manual"


def _with_options(statement):
    return statement.options(selectinload(Vehicle.options).joinedload(VehicleOption.definition))


def get_vehicle(session: Session, vehicle_id: int) -> Vehicle | None:
    return (
        session.scalars(_with_options(select(Vehicle).where(Vehicle.id == vehicle_id)))
        .unique()
        .one_or_none()
    )


def find_by_license_plate(session: Session, plate: str) -> Vehicle | None:
    """Look up a plate in the local dataset only.

    No external service is contacted: the MVP knows the vehicles it has been
    given, and says so when it does not recognise a plate.
    """
    normalized = normalization.normalize_license_plate(plate)
    if not normalized:
        return None
    return (
        session.scalars(_with_options(select(Vehicle).where(Vehicle.license_plate == normalized)))
        .unique()
        .first()
    )


def is_demo_vehicle(vehicle: Vehicle) -> bool:
    """Whether a stored vehicle exists only as demonstration data.

    The synthetic market invents plausible Dutch plates, and plausible plates
    collide with real ones: BB-100-B belongs to a real lorry and to a fictional
    BMW in our seed. Demo data may illustrate the product, but it can never
    answer "which car is this plate?".

    A vehicle with no listings was entered by hand or built from a register
    lookup, so it is real to the person who entered it.
    """
    listings = vehicle.listings
    if not listings:
        return False
    return all(
        listing.data_source is not None
        and listing.data_source.source_type is DataSourceType.SYNTHETIC
        for listing in listings
    )


def find_real_by_license_plate(session: Session, plate: str) -> Vehicle | None:
    """Look up a plate typed by a user, ignoring demonstration data.

    Used wherever a plate is treated as a claim about a real vehicle. The demo
    cars stay reachable, but only through an explicit choice by id — never by
    typing a plate that happens to collide with one.
    """
    vehicle = find_by_license_plate(session, plate)
    if vehicle is None or is_demo_vehicle(vehicle):
        return None
    return vehicle


def ensure_manual_data_source(session: Session) -> DataSource:
    data_source = session.scalar(select(DataSource).where(DataSource.key == MANUAL_SOURCE_KEY))
    if data_source is None:
        data_source = DataSource(
            key=MANUAL_SOURCE_KEY,
            source_type=DataSourceType.MANUAL,
            name="Handmatige invoer",
            # User-entered specifications are as good as the user's knowledge.
            quality=0.6,
        )
        session.add(data_source)
        session.flush()
    return data_source


def create_manual_vehicle(session: Session, raw: RawVehicle) -> Vehicle:
    """Create a vehicle from user input, normalizing it on the way in."""
    sync_option_definitions(session)
    ensure_manual_data_source(session)

    definitions = {row.key: row for row in session.scalars(select(VehicleOptionDefinition)).all()}
    options, trim_labels, unresolved = split_option_texts(list(raw.option_texts))

    make = normalization.normalize_make(raw.make)
    model = normalization.normalize_model(make, raw.model)
    trim = normalization.normalize_trim(raw.trim) or (trim_labels[0] if trim_labels else None)

    vehicle = Vehicle(
        license_plate=normalization.normalize_license_plate(raw.license_plate),
        make=make,
        model=model,
        generation=normalization.collapse_whitespace(raw.generation) if raw.generation else None,
        trim=trim,
        make_raw=raw.make,
        model_raw=raw.model,
        trim_raw=raw.trim,
        body_type=normalization.normalize_body_type(raw.body_type),
        fuel_type=normalization.normalize_fuel_type(raw.fuel_type),
        transmission=normalization.normalize_transmission(raw.transmission),
        drivetrain=normalization.normalize_drivetrain(raw.drivetrain),
        engine_description=normalization.normalize_engine_description(raw.engine_description),
        power_hp=raw.power_hp,
        power_kw=raw.power_kw,
        year=raw.year,
        mileage_km=raw.mileage_km,
        source_metadata=json.dumps({"entry": "manual", "unresolved_options": unresolved}),
    )

    for option, raw_text in options:
        definition = definitions.get(option.key)
        if definition is not None:
            vehicle.options.append(VehicleOption(definition_id=definition.id, raw_text=raw_text))

    session.add(vehicle)
    session.flush()
    session.refresh(vehicle)
    return vehicle


def load_vehicle_with_options(session: Session, vehicle_id: int) -> Vehicle | None:
    return (
        session.scalars(
            select(Vehicle)
            .where(Vehicle.id == vehicle_id)
            .options(joinedload(Vehicle.options).joinedload(VehicleOption.definition))
        )
        .unique()
        .one_or_none()
    )
