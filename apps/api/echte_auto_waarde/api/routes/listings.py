"""Listing and market endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC
from itertools import zip_longest
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from echte_auto_waarde.api.mapping import to_listing_read
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.listing import DataSource, Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.valuation import (
    ExampleVehicleRead,
    ListingHistoryRead,
    ListingRead,
    ListingSnapshotRead,
    MarketStatsRead,
)

router = APIRouter(tags=["market"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such listing in the local dataset."}
}


def _get_listing(session: Session, listing_id: int) -> Listing:
    listing = (
        session.scalars(
            select(Listing)
            .where(Listing.id == listing_id)
            .options(
                joinedload(Listing.vehicle)
                .selectinload(Vehicle.options)
                .joinedload(VehicleOption.definition),
                joinedload(Listing.seller),
                joinedload(Listing.data_source),
                selectinload(Listing.snapshots),
            )
        )
        .unique()
        .one_or_none()
    )
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Listing {listing_id} not found."
        )
    return listing


@router.get("/listings/{listing_id}", response_model=ListingRead, responses=NOT_FOUND)
def get_listing(listing_id: int, session: Session = Depends(get_session)) -> ListingRead:
    return to_listing_read(_get_listing(session, listing_id))


@router.get(
    "/listings/{listing_id}/history", response_model=ListingHistoryRead, responses=NOT_FOUND
)
def get_listing_history(
    listing_id: int, session: Session = Depends(get_session)
) -> ListingHistoryRead:
    """Observed history of one listing.

    Only what was actually observed is returned. Nothing here infers that a
    disappeared listing was sold.
    """
    listing = _get_listing(session, listing_id)
    snapshots = sorted(listing.snapshots, key=lambda snapshot: snapshot.observed_at)

    first_seen = listing.first_seen_at
    last_seen = listing.last_seen_at
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=UTC)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)

    price_change = (
        snapshots[-1].asking_price_cents - snapshots[0].asking_price_cents
        if len(snapshots) >= 2
        else 0
    )

    return ListingHistoryRead(
        listing_id=listing.id,
        days_listed=(last_seen - first_seen).days,
        price_change_cents=price_change,
        snapshots=[
            ListingSnapshotRead(
                observed_at=snapshot.observed_at,
                asking_price_cents=snapshot.asking_price_cents,
                mileage_km=snapshot.mileage_km,
                status=snapshot.status.value,
            )
            for snapshot in snapshots
        ],
    )


@router.get("/market/stats", response_model=MarketStatsRead)
def get_market_stats(session: Session = Depends(get_session)) -> MarketStatsRead:
    """What the local dataset actually contains, including where it came from."""
    listing_count = session.scalar(select(func.count()).select_from(Listing)) or 0
    vehicle_count = session.scalar(select(func.count()).select_from(Vehicle)) or 0
    make_count = session.scalar(select(func.count(distinct(Vehicle.make)))) or 0
    model_count = (
        session.scalar(
            select(func.count()).select_from(
                select(Vehicle.make, Vehicle.model).distinct().subquery()
            )
        )
        or 0
    )

    prices = sorted(session.scalars(select(Listing.asking_price_cents)).all())
    average_mileage = session.scalar(select(func.avg(Vehicle.mileage_km)))
    sources = session.scalars(select(DataSource)).all()

    return MarketStatsRead(
        listing_count=listing_count,
        vehicle_count=vehicle_count,
        make_count=make_count,
        model_count=model_count,
        median_price_cents=prices[len(prices) // 2] if prices else None,
        min_price_cents=prices[0] if prices else None,
        max_price_cents=prices[-1] if prices else None,
        average_mileage_km=int(average_mileage) if average_mileage else None,
        data_sources=[source.key for source in sources],
        # True while any listing still comes from the synthetic adapter.
        is_synthetic=any(source.source_type is DataSourceType.SYNTHETIC for source in sources),
    )


@router.get("/market/examples", response_model=list[ExampleVehicleRead])
def get_market_examples(
    limit: int = Query(default=6, ge=1, le=24), session: Session = Depends(get_session)
) -> list[ExampleVehicleRead]:
    """Real vehicles from the local dataset, one per model line.

    The interface needs something to start from: without this, trying the
    product locally would mean guessing a license plate. Spreading the results
    over distinct model lines shows the breadth of the dataset rather than a
    dozen near-identical cars.
    """
    listings = session.scalars(
        select(Listing)
        .join(Vehicle, Listing.vehicle_id == Vehicle.id)
        .options(joinedload(Listing.vehicle))
        .order_by(Vehicle.make, Vehicle.model, Listing.id)
    ).unique()

    # One candidate per model line, grouped by make.
    by_make: dict[str, list[ExampleVehicleRead]] = defaultdict(list)
    seen_model_lines: set[tuple[str, str, str | None]] = set()
    for listing in listings:
        vehicle = listing.vehicle
        key = (vehicle.make, vehicle.model, vehicle.engine_description)
        if key in seen_model_lines:
            continue
        seen_model_lines.add(key)
        by_make[vehicle.make].append(
            ExampleVehicleRead(
                vehicle_id=vehicle.id,
                license_plate=vehicle.license_plate,
                make=vehicle.make,
                model=vehicle.model,
                year=vehicle.year,
                mileage_km=vehicle.mileage_km,
                trim=vehicle.trim,
                engine_description=vehicle.engine_description,
                asking_price_cents=listing.asking_price_cents,
            )
        )

    # Take one per make before offering a second of any make, so a short list
    # shows the breadth of the dataset instead of one alphabetically lucky brand.
    examples: list[ExampleVehicleRead] = []
    for candidates in zip_longest(*by_make.values()):
        for candidate in candidates:
            if candidate is None:
                continue
            examples.append(candidate)
            if len(examples) >= limit:
                return examples

    return examples
