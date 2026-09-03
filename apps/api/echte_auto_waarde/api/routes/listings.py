"""Listing and market endpoints."""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from echte_auto_waarde.api.mapping import to_listing_read
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.listing import DataSource, Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.valuation import (
    ListingHistoryRead,
    ListingRead,
    ListingSnapshotRead,
    MarketStatsRead,
)

router = APIRouter(tags=["market"])


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


@router.get("/listings/{listing_id}", response_model=ListingRead)
def get_listing(listing_id: int, session: Session = Depends(get_session)) -> ListingRead:
    return to_listing_read(_get_listing(session, listing_id))


@router.get("/listings/{listing_id}/history", response_model=ListingHistoryRead)
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
