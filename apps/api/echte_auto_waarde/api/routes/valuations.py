"""Valuation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from echte_auto_waarde.api.deps import build_criteria, resolve_target_vehicle
from echte_auto_waarde.api.mapping import stored_valuation_to_read, to_valuation_read
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.valuation import Valuation
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.valuation import ValuationRead, ValuationRequest
from echte_auto_waarde.services.comparables import find_comparables
from echte_auto_waarde.services.valuation import store_valuation, valuate_vehicle

router = APIRouter(prefix="/valuations", tags=["valuations"])

# A valuation can be requested for a vehicle or plate that does not exist,
# and a stored valuation can be asked for by an id that never existed.
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such vehicle, plate or valuation."}
}


@router.post("", response_model=ValuationRead, responses=NOT_FOUND)
def create_valuation(
    request: ValuationRequest, session: Session = Depends(get_session)
) -> ValuationRead:
    """Value a vehicle against comparable market listings.

    Thin evidence is reported as an insufficient-data result (HTTP 200 with
    sufficientData false), never as a fabricated number.
    """
    vehicle = resolve_target_vehicle(session, request)
    criteria = build_criteria(request.criteria)

    selection = find_comparables(session, vehicle, criteria)
    result = valuate_vehicle(
        session, vehicle, asking_price_cents=request.asking_price_cents, criteria=criteria
    )

    valuation_id = None
    if result.sufficient_data:
        valuation_id = store_valuation(session, vehicle, result).id

    response = to_valuation_read(session, vehicle, result, selection, valuation_id)
    session.commit()
    return response


@router.get("/{valuation_id}", response_model=ValuationRead, responses=NOT_FOUND)
def get_valuation(valuation_id: int, session: Session = Depends(get_session)) -> ValuationRead:
    """Return a stored valuation with the evidence it was based on."""
    valuation = (
        session.scalars(
            select(Valuation)
            .where(Valuation.id == valuation_id)
            .options(
                joinedload(Valuation.target_vehicle)
                .selectinload(Vehicle.options)
                .joinedload(VehicleOption.definition),
                selectinload(Valuation.comparables),
            )
        )
        .unique()
        .one_or_none()
    )

    if valuation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valuation {valuation_id} not found.",
        )

    return stored_valuation_to_read(session, valuation)
