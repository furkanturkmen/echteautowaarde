"""Loading comparable candidates from the database.

The database narrows to the model line (which is what an index can do well); the
domain engine decides everything else. Keeping the split here means the
comparable rules stay testable without a database and identical no matter which
data source the listings came from.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from echte_auto_waarde.domain.comparables import (
    DEFAULT_CRITERIA,
    ComparableCandidate,
    ComparableCriteria,
    ComparableSelection,
    select_comparables,
)
from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.models.enums import ListingStatus
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.vehicle import Vehicle

# A removed listing is no longer an offer, so it cannot be current market
# evidence. It stays in the database for historical analysis.
EXCLUDED_STATUSES = (ListingStatus.REMOVED,)


def load_candidates(
    session: Session,
    target: Vehicle,
    exclude_vehicle_id: int | None = None,
) -> list[ComparableCandidate]:
    """Load every listing on the same model line as the target vehicle."""
    statement = (
        select(Listing)
        .join(Vehicle, Listing.vehicle_id == Vehicle.id)
        .where(
            Vehicle.make == target.make,
            Vehicle.model == target.model,
            Listing.status.not_in(EXCLUDED_STATUSES),
        )
        .options(
            joinedload(Listing.vehicle)
            .selectinload(Vehicle.options)
            .joinedload(VehicleOption.definition),
            joinedload(Listing.data_source),
        )
    )

    exclude_id = exclude_vehicle_id if exclude_vehicle_id is not None else target.id
    if exclude_id is not None:
        statement = statement.where(Vehicle.id != exclude_id)

    candidates: list[ComparableCandidate] = []
    for listing in session.scalars(statement).unique():
        candidates.append(
            ComparableCandidate(
                listing_id=listing.id,
                fingerprint=VehicleFingerprint.from_vehicle(listing.vehicle),
                asking_price_cents=listing.asking_price_cents,
                last_seen_at=listing.last_seen_at,
                seller_type=listing.seller.seller_type if listing.seller else None,
                source_quality=listing.data_source.quality if listing.data_source else 0.5,
            )
        )
    return candidates


def find_comparables(
    session: Session,
    target: Vehicle,
    criteria: ComparableCriteria = DEFAULT_CRITERIA,
    exclude_vehicle_id: int | None = None,
) -> ComparableSelection:
    """Find comparables for a target vehicle, widening only if needed."""
    candidates = load_candidates(session, target, exclude_vehicle_id=exclude_vehicle_id)
    fingerprint = VehicleFingerprint.from_vehicle(target)
    return select_comparables(fingerprint, candidates, criteria)
