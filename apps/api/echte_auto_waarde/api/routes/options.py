"""Option taxonomy endpoint.

Manual vehicle entry needs the canonical options the engine actually knows
about. Exposing the taxonomy means the interface can offer real Dutch labels
instead of asking the user to guess wording that happens to normalize.
"""

from __future__ import annotations

from fastapi import APIRouter

from echte_auto_waarde.domain.options import OPTION_TAXONOMY
from echte_auto_waarde.schemas.vehicle import VehicleOptionRead

router = APIRouter(prefix="/options", tags=["options"])


@router.get("", response_model=list[VehicleOptionRead])
def list_options() -> list[VehicleOptionRead]:
    """Every canonical option, including how much each one matters."""
    return [
        VehicleOptionRead(
            key=definition.key,
            label_nl=definition.label_nl,
            category=definition.category.value,
            importance=definition.importance,
        )
        for definition in OPTION_TAXONOMY
    ]
