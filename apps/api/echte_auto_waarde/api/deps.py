"""Shared API helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawVehicle
from echte_auto_waarde.domain.comparables import DEFAULT_CRITERIA, ComparableCriteria
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.valuation import ComparableCriteriaInput, ValuationRequest
from echte_auto_waarde.services import vehicles as vehicle_service


def resolve_target_vehicle(session: Session, request: ValuationRequest) -> Vehicle:
    """Resolve the vehicle a request is about: by id, plate, or manual entry."""
    if request.vehicle_id is not None:
        vehicle = vehicle_service.get_vehicle(session, request.vehicle_id)
        if vehicle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vehicle {request.vehicle_id} not found.",
            )
        return vehicle

    if request.license_plate:
        vehicle = vehicle_service.find_by_license_plate(session, request.license_plate)
        if vehicle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "License plate not found in the local dataset. "
                    "Enter the vehicle manually to continue."
                ),
            )
        return vehicle

    if request.manual_vehicle is not None:
        payload = request.manual_vehicle
        return vehicle_service.create_manual_vehicle(
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

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Provide vehicleId, licensePlate or manualVehicle.",
    )


def build_criteria(overrides: ComparableCriteriaInput | None) -> ComparableCriteria:
    """Apply per-request preferences on top of the documented defaults."""
    if overrides is None:
        return DEFAULT_CRITERIA

    return ComparableCriteria(
        min_similarity=(
            overrides.min_similarity
            if overrides.min_similarity is not None
            else DEFAULT_CRITERIA.min_similarity
        ),
        min_comparables=DEFAULT_CRITERIA.min_comparables,
        max_comparables=(
            overrides.max_comparables
            if overrides.max_comparables is not None
            else DEFAULT_CRITERIA.max_comparables
        ),
        max_year_gap=DEFAULT_CRITERIA.max_year_gap,
        weights=DEFAULT_CRITERIA.weights,
        required_option_keys=frozenset(overrides.required_option_keys),
        require_same_transmission=overrides.require_same_transmission,
        require_same_engine=overrides.require_same_engine,
    )
