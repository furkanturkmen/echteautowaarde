"""Vehicle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawVehicle
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.schemas.vehicle import ManualVehicleCreate, VehicleRead
from echte_auto_waarde.services import vehicles as vehicle_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(vehicle_id: int, session: Session = Depends(get_session)) -> VehicleRead:
    vehicle = vehicle_service.get_vehicle(session, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Vehicle {vehicle_id} not found."
        )
    return VehicleRead.from_vehicle(vehicle)


@router.get("/plate/{plate}", response_model=VehicleRead)
def get_vehicle_by_plate(plate: str, session: Session = Depends(get_session)) -> VehicleRead:
    """Look up a plate in the local dataset.

    No external service is contacted; an unknown plate is reported as unknown so
    the user can enter the vehicle manually instead.
    """
    vehicle = vehicle_service.find_by_license_plate(session, plate)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "License plate not found in the local dataset. "
                "Enter the vehicle manually to continue."
            ),
        )
    return VehicleRead.from_vehicle(vehicle)


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
