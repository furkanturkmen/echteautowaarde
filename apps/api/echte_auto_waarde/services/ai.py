"""AI explanation service.

Loads the stored valuation, builds the structured context from it, asks the
provider, and verifies the answer before returning it. The client sends an id
and a question and nothing else that matters: every figure the assistant sees
comes from the database, so a tampered request cannot change what is explained.

Every failure degrades. The caller always receives a result object; the AI being
down is a state of this endpoint, never an error of the application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from echte_auto_waarde.ai.grounding import GroundingResult, check_answer
from echte_auto_waarde.ai.prompt import build_system_prompt, build_user_prompt
from echte_auto_waarde.ai.provider import (
    AIProvider,
    AIResponseError,
    AITimeoutError,
    AIUnavailableError,
)
from echte_auto_waarde.domain.ai_context import (
    MAX_CONTEXT_COMPARABLES,
    MAX_CONTEXT_OPTIONS,
    AdjustmentContext,
    ComparableContext,
    ConfidenceFactorContext,
    ValuationAiContext,
)
from echte_auto_waarde.domain.evidence import describe_evidence
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.models.option import VehicleOption
from echte_auto_waarde.models.valuation import Valuation
from echte_auto_waarde.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = (
    "AI-uitleg is lokaal niet beschikbaar. De waardering en vergelijkbare auto's "
    "blijven gewoon beschikbaar."
)


@dataclass
class AiAnswer:
    """What the endpoint returns, available or not."""

    available: bool
    provider: str
    model: str
    answer: str | None = None
    # Amounts only. A grounded answer can still get a relationship wrong; the
    # check reads euro figures, not meaning.
    grounded: bool = True
    grounding_note: str | None = None
    unavailable_reason: str | None = None


def load_valuation_for_ai(session: Session, valuation_id: int) -> Valuation | None:
    return (
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


def build_context(session: Session, valuation: Valuation) -> ValuationAiContext:
    """Turn a stored valuation into the structured context, and nothing more."""
    vehicle = valuation.target_vehicle

    records = sorted(
        valuation.comparables, key=lambda record: record.similarity_score, reverse=True
    )[:MAX_CONTEXT_COMPARABLES]
    listings = _load_listings(session, [record.listing_id for record in records])

    comparables: list[ComparableContext] = []
    for record in records:
        listing = listings.get(record.listing_id)
        if listing is None:
            continue
        price = record.adjusted_price_cents or listing.asking_price_cents
        comparables.append(
            ComparableContext(
                similarity=record.similarity_score,
                make=listing.vehicle.make,
                model=listing.vehicle.model,
                year=listing.vehicle.year,
                mileage_km=listing.vehicle.mileage_km,
                trim=listing.vehicle.trim,
                engine_description=listing.vehicle.engine_description,
                asking_price_cents=price,
                price_difference_cents=price - valuation.estimated_market_value_cents,
                seller_type=listing.seller.seller_type.value if listing.seller else None,
                reasons=[str(entry.get("code")) for entry in (record.reasons or [])],
                differences=[str(entry.get("code")) for entry in (record.differences or [])],
            )
        )

    sources = {
        listing.data_source.source_type for listing in listings.values() if listing.data_source
    }

    return ValuationAiContext(
        valuation_id=valuation.id,
        algorithm_version=valuation.algorithm_version,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        mileage_km=vehicle.mileage_km,
        trim=vehicle.trim,
        engine_description=vehicle.engine_description,
        fuel_type=vehicle.fuel_type.value,
        transmission=vehicle.transmission.value,
        body_type=vehicle.body_type.value,
        power_hp=vehicle.power_hp,
        license_plate=vehicle.license_plate,
        options=[
            option.definition.label_nl
            for option in vehicle.options[:MAX_CONTEXT_OPTIONS]
            if option.definition
        ],
        estimated_market_value_cents=valuation.estimated_market_value_cents,
        recommended_buy_price_low_cents=valuation.recommended_buy_price_low_cents,
        recommended_buy_price_high_cents=valuation.recommended_buy_price_high_cents,
        market_basis_cents=valuation.market_basis_cents,
        asking_price_cents=valuation.asking_price_cents,
        deal_classification=(
            valuation.deal_classification.value if valuation.deal_classification else None
        ),
        confidence_score=valuation.confidence_score,
        confidence_factors=[
            ConfidenceFactorContext(
                code=str(factor.get("code")),
                impact=str(factor.get("impact")),
                score=float(factor.get("score", 0.0)),
                detail={
                    key: value
                    for key, value in factor.items()
                    if key not in {"code", "impact", "score", "weight"}
                },
            )
            for factor in (valuation.confidence_factors or [])
        ],
        comparable_count=valuation.comparable_count,
        widening_level=valuation.widening_level,
        market_statistics=valuation.market_statistics or {},
        adjustments=[
            AdjustmentContext(
                type=str(adjustment.get("type")),
                amount_cents=int(adjustment.get("amountCents", 0)),
                reason=str(adjustment.get("reason", "")),
                detail=dict(adjustment.get("detail") or {}),
            )
            for adjustment in (valuation.adjustments or [])
        ],
        comparables=comparables,
        # Whether the evidence is invented decides how the assistant may speak
        # about it, so it travels with the context rather than being assumed.
        data_is_synthetic=DataSourceType.SYNTHETIC in sources or not sources,
        # The same sentence the interface shows, derived from the same evidence,
        # so the assistant and the page cannot disagree about provenance.
        data_disclaimer=describe_evidence(sources),
    )


def answer_question(
    session: Session,
    valuation: Valuation,
    question: str,
    provider: AIProvider,
) -> AiAnswer:
    """Answer one question about one stored valuation."""
    context = build_context(session, valuation)

    if not provider.is_available():
        return AiAnswer(
            available=False,
            provider=provider.name,
            model=provider.model,
            unavailable_reason=UNAVAILABLE_MESSAGE,
        )

    try:
        raw = provider.generate(build_system_prompt(context), build_user_prompt(context, question))
    except AITimeoutError:
        logger.info("AI generation timed out for valuation %s", valuation.id)
        return AiAnswer(
            available=False,
            provider=provider.name,
            model=provider.model,
            unavailable_reason=(
                "Het lokale model reageerde niet op tijd. De waardering hierboven blijft "
                "gewoon beschikbaar."
            ),
        )
    except (AIUnavailableError, AIResponseError) as error:
        logger.info("AI unavailable for valuation %s: %s", valuation.id, error)
        return AiAnswer(
            available=False,
            provider=provider.name,
            model=provider.model,
            unavailable_reason=UNAVAILABLE_MESSAGE,
        )

    grounding: GroundingResult = check_answer(raw, context)
    if not grounding.grounded:
        logger.warning(
            "AI answer for valuation %s mentioned %d amount(s) outside the context",
            valuation.id,
            len(grounding.unknown_amounts_cents),
        )

    return AiAnswer(
        available=True,
        provider=provider.name,
        model=provider.model,
        answer=raw,
        grounded=grounding.grounded,
        grounding_note=grounding.note,
    )


def _load_listings(session: Session, listing_ids: list[int]) -> dict[int, Listing]:
    if not listing_ids:
        return {}
    statement = (
        select(Listing)
        .where(Listing.id.in_(listing_ids))
        .options(
            joinedload(Listing.vehicle),
            joinedload(Listing.seller),
            joinedload(Listing.data_source),
        )
    )
    return {listing.id: listing for listing in session.scalars(statement).unique()}
