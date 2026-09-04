"""Running the valuation engine against imported market evidence.

Leave-one-out: every eligible listing becomes a target in turn, is valued
against every other listing but itself, and the result is compared with the
asking price that was actually observed for it.

Two things make that honest. The target listing is excluded at the comparable
boundary, so a listing can never be evidence for its own valuation. And the
production valuation code does the work — this module selects targets and
collects results, and reimplements nothing.

Nothing is written. No `Valuation` rows are created, so an evaluation run leaves
consumer history exactly as it was.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from echte_auto_waarde.domain.evaluation import (
    DEFAULT_OUTLIER_COUNT,
    MIN_SEGMENT_SIZE,
    STANDARD_SEGMENTS,
    EvaluationReport,
    ListingEvaluation,
    largest_deviations,
    segment_by,
    summarise,
)
from echte_auto_waarde.domain.evidence import REAL_SOURCE_TYPES
from echte_auto_waarde.models.enums import ListingStatus
from echte_auto_waarde.models.listing import DataSource, Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.valuation import valuate_vehicle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationFilters:
    """Which listings to evaluate. Evidence is always the whole real market."""

    source_key: str | None = None
    scope: str | None = None
    make: str | None = None
    model: str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def describe(self) -> str:
        parts = [
            f"source={self.source_key}" if self.source_key else None,
            f"scope={self.scope}" if self.scope else None,
            f"make={self.make}" if self.make else None,
            f"model={self.model}" if self.model else None,
            f"year>={self.year_from}" if self.year_from else None,
            f"year<={self.year_to}" if self.year_to else None,
        ]
        chosen = [part for part in parts if part]
        return ", ".join(chosen) if chosen else "all imported market evidence"


def select_targets(session: Session, filters: EvaluationFilters) -> list[Listing]:
    """Eligible target listings, in a deterministic order.

    Only real evidence: synthetic demo listings are never evaluated and never
    participate, whatever this installation's market mode says. Removed listings
    are excluded — they are no longer an offer.
    """
    statement = (
        select(Listing)
        .join(Vehicle, Listing.vehicle_id == Vehicle.id)
        .join(DataSource, Listing.data_source_id == DataSource.id)
        .where(
            DataSource.source_type.in_(REAL_SOURCE_TYPES),
            Listing.status != ListingStatus.REMOVED,
            Listing.asking_price_cents > 0,
        )
        .options(
            joinedload(Listing.vehicle)
            .selectinload(Vehicle.options)
            .joinedload(VehicleOption.definition),
            joinedload(Listing.data_source),
        )
        .order_by(Listing.id)
    )

    if filters.source_key:
        statement = statement.where(DataSource.key == filters.source_key)
    if filters.scope:
        statement = statement.where(Listing.source_scope == filters.scope)
    if filters.make:
        statement = statement.where(Vehicle.make == filters.make)
    if filters.model:
        statement = statement.where(Vehicle.model == filters.model)
    if filters.year_from:
        statement = statement.where(Vehicle.year >= filters.year_from)
    if filters.year_to:
        statement = statement.where(Vehicle.year <= filters.year_to)

    return list(session.scalars(statement).unique())


def evaluate_listing(session: Session, listing: Listing) -> ListingEvaluation:
    """Value one listing against the rest of the real market."""
    vehicle = listing.vehicle
    result = valuate_vehicle(
        session,
        vehicle,
        # The asking price is what we compare against, so it is deliberately not
        # handed to the engine: it must not influence the estimate it is
        # measured against.
        asking_price_cents=None,
        exclude_listing_id=listing.id,
        evidence_sources=REAL_SOURCE_TYPES,
    )

    similarities = [item.score for item in result.comparables]
    references = _comparable_references(
        session, [item.candidate.listing_id for item in result.comparables]
    )

    return ListingEvaluation(
        listing_id=listing.id,
        external_reference=listing.external_reference,
        source_key=listing.data_source.key if listing.data_source else "unknown",
        scope=listing.source_scope,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        mileage_km=vehicle.mileage_km,
        trim=vehicle.trim,
        fuel_type=vehicle.fuel_type.value,
        transmission=vehicle.transmission.value,
        body_type=vehicle.body_type.value,
        observed_asking_price_cents=listing.asking_price_cents,
        estimated_market_value_cents=result.estimated_market_value_cents,
        sufficient_data=result.sufficient_data,
        comparable_count=len(result.comparables),
        widening_level=result.widening_level,
        confidence_score=result.confidence.score if result.confidence else None,
        mean_similarity=fmean(similarities) if similarities else None,
        comparable_references=references,
        adjustments=tuple((item.type, item.amount_cents) for item in result.adjustments),
        insufficient_data_reason=result.insufficient_data_reason,
    )


def evaluate_market(
    session: Session,
    filters: EvaluationFilters | None = None,
    outlier_count: int = DEFAULT_OUTLIER_COUNT,
    minimum_segment_size: int = MIN_SEGMENT_SIZE,
) -> EvaluationReport:
    """Evaluate every eligible listing and describe the result.

    Deterministic: targets are ordered by id, the valuation engine is
    deterministic, and so the same database produces the same report.
    """
    filters = filters or EvaluationFilters()
    targets = select_targets(session, filters)
    logger.info("Evaluating %d listing(s) against imported market evidence", len(targets))

    evaluations = [evaluate_listing(session, listing) for listing in targets]

    segments = {
        name: segment_by(evaluations, key, minimum_size=minimum_segment_size)
        for name, key in STANDARD_SEGMENTS.items()
    }

    return EvaluationReport(
        dataset=filters.describe(),
        listing_count=len(evaluations),
        overall=summarise(evaluations),
        segments={name: found for name, found in segments.items() if found},
        outliers=largest_deviations(evaluations, limit=outlier_count),
        minimum_segment_size=minimum_segment_size,
    )


def _comparable_references(session: Session, listing_ids: list[int]) -> tuple[str, ...]:
    """External references of the evidence used, for diagnosis."""
    if not listing_ids:
        return ()
    rows = session.execute(
        select(Listing.id, Listing.external_reference).where(Listing.id.in_(listing_ids))
    ).all()
    by_id = {row.id: row.external_reference for row in rows}
    return tuple(by_id[listing_id] for listing_id in listing_ids if listing_id in by_id)
