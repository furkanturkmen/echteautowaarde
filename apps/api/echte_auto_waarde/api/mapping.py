"""Mapping between domain results and API schemas.

Kept separate from both the domain and the routes: the engine should not know
about HTTP, and route handlers should not contain assembly logic.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from echte_auto_waarde.domain.comparables import (
    WIDENING_LEVELS,
    ComparableSelection,
    ScoredComparable,
)
from echte_auto_waarde.domain.evidence import describe_evidence
from echte_auto_waarde.domain.valuation import ValuationResult
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.valuation import Valuation
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.valuation import (
    AdjustmentRead,
    ComparableRead,
    ComparableSearchRead,
    ConfidenceFactorRead,
    ListingRead,
    MarketStatisticsRead,
    SimilarityEntry,
    ValuationRead,
)
from echte_auto_waarde.schemas.vehicle import VehicleRead

# Keys that carry their own schema field; anything else is passed through as
# free-form detail so new confidence factors need no schema change.
_FACTOR_FIELDS = {"code", "impact", "score", "weight"}


def _widening_description(level: int) -> str | None:
    """The stored level's description, so a retrieved valuation explains its own scope."""
    return next(
        (description for value, description in WIDENING_LEVELS if value == level),
        None,
    )


def load_listings(session: Session, listing_ids: list[int]) -> dict[int, Listing]:
    if not listing_ids:
        return {}
    statement = (
        select(Listing)
        .where(Listing.id.in_(listing_ids))
        .options(
            joinedload(Listing.vehicle)
            .selectinload(Vehicle.options)
            .joinedload(VehicleOption.definition),
            joinedload(Listing.seller),
            joinedload(Listing.data_source),
        )
    )
    return {listing.id: listing for listing in session.scalars(statement).unique()}


def _entries(items: list[dict]) -> list[SimilarityEntry]:
    return [SimilarityEntry(**item) for item in items]


def to_comparable_read(
    item: ScoredComparable,
    listing: Listing | None,
    reference_price_cents: int | None = None,
) -> ComparableRead | None:
    if listing is None:
        return None
    return ComparableRead(
        listing_id=listing.id,
        similarity=item.score,
        asking_price_cents=item.asking_price_cents,
        price_difference_cents=(
            item.asking_price_cents - reference_price_cents
            if reference_price_cents is not None
            else None
        ),
        seller_type=listing.seller.seller_type.value if listing.seller else None,
        observed_at=listing.last_seen_at,
        vehicle=VehicleRead.from_vehicle(listing.vehicle),
        reasons=_entries(item.similarity.reasons),
        differences=_entries(item.similarity.differences),
    )


def evidence_disclaimer(listings: dict[int, Listing]) -> str:
    """Say what this particular valuation rests on.

    Derived from the listings behind it rather than assumed, so an imported
    market is never described as a demo market or the other way round.
    """
    sources = {
        listing.data_source.source_type
        for listing in listings.values()
        if listing.data_source is not None
    }
    return describe_evidence(sources)


def to_valuation_read(
    session: Session,
    vehicle: Vehicle,
    result: ValuationResult,
    selection: ComparableSelection | None = None,
    valuation_id: int | None = None,
) -> ValuationRead:
    listings = load_listings(session, [item.candidate.listing_id for item in result.comparables])
    reference = result.estimated_market_value_cents

    comparables = [
        read
        for read in (
            to_comparable_read(item, listings.get(item.candidate.listing_id), reference)
            for item in result.comparables
        )
        if read is not None
    ]

    return ValuationRead(
        id=valuation_id,
        data_disclaimer=evidence_disclaimer(listings),
        sufficient_data=result.sufficient_data,
        algorithm_version=result.algorithm_version,
        vehicle=VehicleRead.from_vehicle(vehicle),
        asking_price_cents=result.asking_price_cents,
        estimated_market_value_cents=result.estimated_market_value_cents,
        recommended_buy_price_low_cents=result.recommended_buy_price_low_cents,
        recommended_buy_price_high_cents=result.recommended_buy_price_high_cents,
        market_basis_cents=result.market_basis_cents,
        deal_classification=result.deal_classification,
        confidence_score=result.confidence.score if result.confidence else None,
        confidence_factors=[
            ConfidenceFactorRead(
                code=factor["code"],
                impact=factor["impact"],
                score=factor["score"],
                weight=factor["weight"],
                detail={key: value for key, value in factor.items() if key not in _FACTOR_FIELDS},
            )
            for factor in (result.confidence.factors if result.confidence else [])
        ],
        comparable_count=result.statistics.comparable_count if result.statistics else 0,
        widening_level=result.widening_level,
        widening_description=selection.widening_description if selection else None,
        market_statistics=(
            # Same serialization as a stored valuation, so creating and
            # re-reading a valuation never report a statistic differently.
            MarketStatisticsRead.model_validate(result.statistics.to_dict())
            if result.statistics
            else None
        ),
        adjustments=[
            AdjustmentRead(
                type=adjustment.type,
                amount_cents=adjustment.amount_cents,
                reason=adjustment.reason,
                detail=adjustment.detail or None,
            )
            for adjustment in result.adjustments
        ],
        comparables=comparables,
        insufficient_data_reason=result.insufficient_data_reason,
        unstated_target_fields=list(result.unstated_target_fields),
    )


def to_comparable_search_read(
    session: Session, vehicle: Vehicle, selection: ComparableSelection
) -> ComparableSearchRead:
    listings = load_listings(session, [item.candidate.listing_id for item in selection.comparables])
    comparables = [
        read
        for read in (
            to_comparable_read(item, listings.get(item.candidate.listing_id))
            for item in selection.comparables
        )
        if read is not None
    ]

    return ComparableSearchRead(
        vehicle=VehicleRead.from_vehicle(vehicle),
        comparable_count=selection.count,
        widening_level=selection.widening_level,
        widening_description=selection.widening_description,
        candidates_considered=selection.candidates_considered,
        rejected_below_threshold=selection.rejected_below_threshold,
        rejected_by_requirements=selection.rejected_by_requirements,
        comparables=comparables,
    )


def to_listing_read(listing: Listing) -> ListingRead:
    return ListingRead(
        id=listing.id,
        asking_price_cents=listing.asking_price_cents,
        status=listing.status.value,
        url=listing.url,
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        seller_type=listing.seller.seller_type.value if listing.seller else None,
        seller_city=listing.seller.city if listing.seller else None,
        data_source=listing.data_source.key if listing.data_source else "unknown",
        vehicle=VehicleRead.from_vehicle(listing.vehicle),
    )


def stored_valuation_to_read(session: Session, valuation: Valuation) -> ValuationRead:
    """Rebuild a response from a stored valuation.

    Comparables come from the stored records rather than a fresh search, so a
    historical valuation keeps showing the evidence it was actually based on
    even after the market has moved.
    """
    listings = load_listings(session, [record.listing_id for record in valuation.comparables])
    statistics = valuation.market_statistics or {}

    comparables: list[ComparableRead] = []
    for record in valuation.comparables:
        listing = listings.get(record.listing_id)
        if listing is None:
            continue
        price = record.adjusted_price_cents or listing.asking_price_cents
        comparables.append(
            ComparableRead(
                listing_id=listing.id,
                similarity=record.similarity_score,
                asking_price_cents=price,
                price_difference_cents=price - valuation.estimated_market_value_cents,
                seller_type=listing.seller.seller_type.value if listing.seller else None,
                observed_at=listing.last_seen_at,
                vehicle=VehicleRead.from_vehicle(listing.vehicle),
                reasons=_entries(record.reasons),
                differences=_entries(record.differences),
            )
        )

    return ValuationRead(
        data_disclaimer=evidence_disclaimer(listings),
        id=valuation.id,
        sufficient_data=True,
        algorithm_version=valuation.algorithm_version,
        vehicle=VehicleRead.from_vehicle(valuation.target_vehicle),
        asking_price_cents=valuation.asking_price_cents,
        estimated_market_value_cents=valuation.estimated_market_value_cents,
        market_basis_cents=valuation.market_basis_cents,
        recommended_buy_price_low_cents=valuation.recommended_buy_price_low_cents,
        recommended_buy_price_high_cents=valuation.recommended_buy_price_high_cents,
        deal_classification=valuation.deal_classification,
        confidence_score=valuation.confidence_score,
        confidence_factors=[
            ConfidenceFactorRead(
                code=factor["code"],
                impact=factor["impact"],
                score=factor["score"],
                weight=factor["weight"],
                detail={key: value for key, value in factor.items() if key not in _FACTOR_FIELDS},
            )
            for factor in valuation.confidence_factors or []
        ],
        comparable_count=valuation.comparable_count,
        widening_level=valuation.widening_level,
        widening_description=_widening_description(valuation.widening_level),
        market_statistics=(MarketStatisticsRead.model_validate(statistics) if statistics else None),
        adjustments=[
            AdjustmentRead(
                type=adjustment["type"],
                amount_cents=adjustment["amountCents"],
                reason=adjustment["reason"],
                detail=adjustment.get("detail"),
            )
            for adjustment in valuation.adjustments or []
        ],
        comparables=comparables,
    )
