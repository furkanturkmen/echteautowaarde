"""Valuation orchestration.

Loads the evidence, runs the deterministic engine, and stores the result with
the algorithm version that produced it so valuations stay comparable across
methodology changes.
"""

from __future__ import annotations

import json
from statistics import mean

from sqlalchemy.orm import Session

from echte_auto_waarde.domain.comparables import DEFAULT_CRITERIA, ComparableCriteria
from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.valuation import (
    DEFAULT_CONFIG,
    ValuationConfig,
    ValuationResult,
    value_vehicle,
)
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.valuation import ComparableResultRecord, Valuation
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.comparables import find_comparables


def valuate_vehicle(
    session: Session,
    target: Vehicle,
    asking_price_cents: int | None = None,
    criteria: ComparableCriteria = DEFAULT_CRITERIA,
    config: ValuationConfig = DEFAULT_CONFIG,
    exclude_listing_id: int | None = None,
    evidence_sources: frozenset[DataSourceType] | None = None,
) -> ValuationResult:
    """Run the full pipeline for one vehicle without storing anything.

    The two exclusion arguments exist for offline evaluation, which values a
    listing against every other listing but itself. They only ever narrow the
    evidence; the methodology below is untouched by them.
    """
    selection = find_comparables(
        session,
        target,
        criteria,
        exclude_listing_id=exclude_listing_id,
        evidence_sources=evidence_sources,
    )
    fingerprint = VehicleFingerprint.from_vehicle(target)

    qualities = [item.candidate.source_quality for item in selection.comparables]
    source_quality = mean(qualities) if qualities else 0.5

    return value_vehicle(
        target=fingerprint,
        selection=selection,
        asking_price_cents=asking_price_cents,
        config=config,
        source_quality=source_quality,
        option_data_complete=_option_data_is_complete(target),
    )


def store_valuation(session: Session, target: Vehicle, result: ValuationResult) -> Valuation:
    """Persist a completed valuation together with the evidence behind it."""
    if not result.sufficient_data:
        raise ValueError("an insufficient-data result must not be stored as a valuation")

    assert result.estimated_market_value_cents is not None
    assert result.recommended_buy_price_low_cents is not None
    assert result.recommended_buy_price_high_cents is not None
    assert result.confidence is not None
    assert result.statistics is not None

    valuation = Valuation(
        target_vehicle_id=target.id,
        asking_price_cents=result.asking_price_cents,
        estimated_market_value_cents=result.estimated_market_value_cents,
        market_basis_cents=result.market_basis_cents,
        recommended_buy_price_low_cents=result.recommended_buy_price_low_cents,
        recommended_buy_price_high_cents=result.recommended_buy_price_high_cents,
        deal_classification=result.deal_classification,
        confidence_score=result.confidence.score,
        comparable_count=result.statistics.comparable_count,
        widening_level=result.widening_level,
        market_statistics=result.statistics.to_dict(),
        adjustments=[adjustment.to_dict() for adjustment in result.adjustments],
        confidence_factors=result.confidence.factors,
        algorithm_version=result.algorithm_version,
    )
    session.add(valuation)
    session.flush()

    for item in result.comparables:
        session.add(
            ComparableResultRecord(
                valuation_id=valuation.id,
                listing_id=item.candidate.listing_id,
                similarity_score=item.score,
                adjusted_price_cents=item.asking_price_cents,
                weight=item.score,
                reasons=item.similarity.reasons,
                differences=item.similarity.differences,
            )
        )

    session.flush()
    return valuation


def _option_data_is_complete(vehicle: Vehicle) -> bool:
    """Whether every option text on this vehicle resolved to the taxonomy.

    Ingestion records unresolved wording in source_metadata; unresolved options
    mean the equipment comparison is incomplete, which lowers confidence.
    """
    if not vehicle.source_metadata:
        return True
    try:
        metadata = json.loads(vehicle.source_metadata)
    except (TypeError, ValueError):
        return True
    return not metadata.get("unresolved_options")
