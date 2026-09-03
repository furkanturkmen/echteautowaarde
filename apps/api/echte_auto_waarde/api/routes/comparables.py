"""Comparable search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from echte_auto_waarde.api.deps import build_criteria, resolve_target_vehicle
from echte_auto_waarde.api.mapping import to_comparable_search_read
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.schemas.valuation import ComparableSearchRead, ComparableSearchRequest
from echte_auto_waarde.services.comparables import find_comparables

router = APIRouter(prefix="/comparables", tags=["comparables"])


@router.post("/search", response_model=ComparableSearchRead)
def search_comparables(
    request: ComparableSearchRequest, session: Session = Depends(get_session)
) -> ComparableSearchRead:
    """Return the comparable vehicles behind a valuation, without valuing."""
    vehicle = resolve_target_vehicle(session, request)
    selection = find_comparables(session, vehicle, build_criteria(request.criteria))
    response = to_comparable_search_read(session, vehicle, selection)
    session.commit()
    return response
