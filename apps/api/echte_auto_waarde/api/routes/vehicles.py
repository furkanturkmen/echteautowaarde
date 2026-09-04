"""Vehicle endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawVehicle, VehicleSpecificationSource
from echte_auto_waarde.data_sources.factory import get_vehicle_source
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.schemas.vehicle import (
    ManualVehicleCreate,
    PlateLookupRead,
    VehicleDraftRead,
    VehicleRead,
)
from echte_auto_waarde.services import plate_lookup as plate_lookup_service
from echte_auto_waarde.services import vehicles as vehicle_service
from echte_auto_waarde.services.plate_lookup import PlateLookupStatus

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

# Every lookup here can miss, and a client reading the schema should see that
# rather than discovering it at runtime.
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such resource in the local dataset."}
}


@router.get("/{vehicle_id}", response_model=VehicleRead, responses=NOT_FOUND)
def get_vehicle(vehicle_id: int, session: Session = Depends(get_session)) -> VehicleRead:
    vehicle = vehicle_service.get_vehicle(session, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Vehicle {vehicle_id} not found."
        )
    return VehicleRead.from_vehicle(vehicle)


@router.get("/plate/{plate}", response_model=VehicleRead, responses=NOT_FOUND)
def get_vehicle_by_plate(plate: str, session: Session = Depends(get_session)) -> VehicleRead:
    """Look up a plate in the local dataset.

    No external service is contacted; an unknown plate is reported as unknown so
    the user can enter the vehicle manually instead.

    Demonstration vehicles are not returned here even when their invented plate
    matches: a plate identifies a real car. They are reachable by id, which is
    what the example list offers.
    """
    vehicle = vehicle_service.find_real_by_license_plate(session, plate)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "License plate not found in the local dataset. "
                "Enter the vehicle manually to continue."
            ),
        )
    return VehicleRead.from_vehicle(vehicle)


# Consumer wording. The register's terms forbid presenting the data as the
# publisher's and forbid their branding, so the register is named, never them.
_MESSAGES = {
    PlateLookupStatus.LOCAL: "Deze auto staat al in onze gegevens.",
    PlateLookupStatus.ENRICHED: (
        "We hebben de gegevens van dit kenteken opgehaald uit het open "
        "kentekenregister. Vul zelf nog aan wat daar niet in staat."
    ),
    PlateLookupStatus.NOT_FOUND: (
        "Dit kenteken kunnen we niet als personenauto terugvinden. "
        "Voer de auto handmatig in om verder te gaan."
    ),
    PlateLookupStatus.UNAVAILABLE: (
        "We konden dit kenteken nu niet opzoeken. Voer de auto handmatig in om verder te gaan."
    ),
}


@router.get("/plate/{plate}/lookup", response_model=PlateLookupRead)
def lookup_plate(
    plate: str,
    session: Session = Depends(get_session),
    source: VehicleSpecificationSource | None = Depends(get_vehicle_source),
) -> PlateLookupRead:
    """Resolve a plate, optionally enriching it from the open vehicle register.

    Local data comes first and a complete local vehicle costs no external call.
    Every outcome is HTTP 200 with a status the interface can act on: this
    answers a question, and "unknown" or "could not reach it" are answers.

    The register describes vehicles, never markets. Mileage, trim, transmission,
    options and prices are not in it, so `missingFields` says what the user
    still has to supply rather than the application inventing it.
    """
    result = plate_lookup_service.lookup_plate(session, plate, source)
    if result.enriched_fields and result.vehicle is not None:
        session.commit()

    draft = None
    if result.draft is not None:
        raw = result.draft
        draft = VehicleDraftRead(
            license_plate=raw.license_plate,
            make=raw.make or None,
            model=raw.model or None,
            year=raw.year,
            first_registration_date=raw.first_registration_date,
            body_type=raw.body_type,
            fuel_type=raw.fuel_type,
            engine_displacement_cc=raw.engine_displacement_cc,
            power_kw=raw.power_kw,
            power_hp=raw.power_hp,
            doors=raw.doors,
            seats=raw.seats,
            color=raw.color,
            catalog_price_cents=raw.catalog_price_cents,
        )

    return PlateLookupRead(
        status=result.status.value,
        plate=result.plate or None,
        vehicle=VehicleRead.from_vehicle(result.vehicle) if result.vehicle else None,
        draft=draft,
        missing_fields=result.missing_fields,
        enriched_fields=result.enriched_fields,
        message=_MESSAGES[result.status],
    )


@router.post("/manual", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
def create_manual_vehicle(
    payload: ManualVehicleCreate, session: Session = Depends(get_session)
) -> VehicleRead:
    vehicle = vehicle_service.create_manual_vehicle(
        session,
        RawVehicle(
            make=payload.make,
            model=payload.model,
            year=payload.year,
            mileage_km=payload.mileage_km,
            trim=payload.trim,
            generation=payload.generation,
            body_type=payload.body_type,
            fuel_type=payload.fuel_type,
            transmission=payload.transmission,
            drivetrain=payload.drivetrain,
            engine_description=payload.engine_description,
            power_hp=payload.power_hp,
            license_plate=payload.license_plate,
            option_texts=tuple(payload.option_texts),
        ),
    )
    session.commit()
    return VehicleRead.from_vehicle(vehicle)
