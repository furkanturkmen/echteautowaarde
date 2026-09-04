"""Valuation, comparable and listing schemas.

A valuation response always carries its own evidence: the comparables it used,
the market statistics they produce, every adjustment applied and the factors
behind the confidence score. A bare number is never a valid response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from echte_auto_waarde.domain.deals import DealClassification
from echte_auto_waarde.domain.evidence import SYNTHETIC_DISCLAIMER
from echte_auto_waarde.schemas.common import ApiModel
from echte_auto_waarde.schemas.vehicle import ManualVehicleCreate, VehicleRead


class ComparableCriteriaInput(ApiModel):
    """Optional per-search preferences.

    This is the hook for "what matters to me": the engine already supports it,
    the interface can expose it when the core flow is proven.
    """

    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    max_comparables: int | None = Field(default=None, ge=1, le=100)
    required_option_keys: list[str] = Field(default_factory=list, max_length=20)
    require_same_transmission: bool = False
    require_same_engine: bool = False


class ValuationRequest(ApiModel):
    """Identify the car to value: by id, by plate, or by manual entry."""

    vehicle_id: int | None = None
    license_plate: str | None = Field(default=None, max_length=16)
    manual_vehicle: ManualVehicleCreate | None = None
    asking_price_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    criteria: ComparableCriteriaInput | None = None


class ComparableSearchRequest(ValuationRequest):
    """Same target selection as a valuation, without producing a value."""


class SimilarityEntry(ApiModel):
    code: str
    field: str | None = None
    value: Any = None
    target_value: Any = None
    delta: float | None = None


class ComparableRead(ApiModel):
    listing_id: int
    similarity: float
    asking_price_cents: int
    price_difference_cents: int | None = None
    seller_type: str | None = None
    observed_at: datetime | None = None
    vehicle: VehicleRead
    reasons: list[SimilarityEntry] = Field(default_factory=list)
    differences: list[SimilarityEntry] = Field(default_factory=list)


class AdjustmentRead(ApiModel):
    type: str
    amount_cents: int
    reason: str
    detail: dict[str, Any] | None = None


class ConfidenceFactorRead(ApiModel):
    code: str
    impact: str
    score: float
    weight: float
    detail: dict[str, Any] = Field(default_factory=dict)


class MarketStatisticsRead(ApiModel):
    comparable_count: int
    min_price_cents: int
    max_price_cents: int
    median_price_cents: int
    weighted_median_price_cents: int
    p25_price_cents: int
    p75_price_cents: int
    relative_dispersion: float
    average_mileage_km: int | None = None
    average_year: float | None = None
    average_similarity: float
    min_similarity: float
    max_similarity: float
    outliers_removed: int


class ValuationRead(ApiModel):
    """A complete valuation, or a documented insufficient-data result."""

    id: int | None = None
    sufficient_data: bool
    algorithm_version: str
    vehicle: VehicleRead
    asking_price_cents: int | None = None

    estimated_market_value_cents: int | None = None
    recommended_buy_price_low_cents: int | None = None
    recommended_buy_price_high_cents: int | None = None
    market_basis_cents: int | None = None
    deal_classification: DealClassification | None = None

    confidence_score: float | None = None
    confidence_factors: list[ConfidenceFactorRead] = Field(default_factory=list)

    comparable_count: int = 0
    widening_level: int = 0
    widening_description: str | None = None
    market_statistics: MarketStatisticsRead | None = None
    adjustments: list[AdjustmentRead] = Field(default_factory=list)
    comparables: list[ComparableRead] = Field(default_factory=list)

    insufficient_data_reason: str | None = None
    # Describes the evidence this valuation actually used — demo market,
    # imported market data, or both — so provenance is never assumed.
    data_disclaimer: str = SYNTHETIC_DISCLAIMER


class ComparableSearchRead(ApiModel):
    vehicle: VehicleRead
    comparable_count: int
    widening_level: int
    widening_description: str
    candidates_considered: int
    rejected_below_threshold: int
    rejected_by_requirements: int
    comparables: list[ComparableRead] = Field(default_factory=list)


class ListingSnapshotRead(ApiModel):
    observed_at: datetime
    asking_price_cents: int
    mileage_km: int | None = None
    status: str


class ListingRead(ApiModel):
    id: int
    asking_price_cents: int
    status: str
    url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    seller_type: str | None = None
    seller_city: str | None = None
    data_source: str
    vehicle: VehicleRead


class ListingHistoryRead(ApiModel):
    listing_id: int
    days_listed: int
    price_change_cents: int
    snapshots: list[ListingSnapshotRead] = Field(default_factory=list)


class MarketStatsRead(ApiModel):
    """Aggregate view of what the local dataset actually contains."""

    listing_count: int
    vehicle_count: int
    make_count: int
    model_count: int
    median_price_cents: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    average_mileage_km: int | None = None
    data_sources: list[str] = Field(default_factory=list)
    is_synthetic: bool = True


class ExampleVehicleRead(ApiModel):
    """A vehicle from the local dataset, offered as a starting point.

    Used by the interface so someone can try the product without inventing a
    license plate. Every field comes from a real seeded listing.
    """

    vehicle_id: int
    license_plate: str | None = None
    make: str
    model: str
    year: int | None = None
    mileage_km: int | None = None
    trim: str | None = None
    engine_description: str | None = None
    asking_price_cents: int


class AiChatRequest(ApiModel):
    """A question about one stored valuation.

    Only the id and the question are accepted. Valuation figures are never taken
    from the client: the server loads the stored valuation and builds the AI
    context from it, so a tampered request cannot change what is explained.
    """

    valuation_id: int = Field(ge=1)
    message: str = Field(min_length=2, max_length=600)


class AiChatRead(ApiModel):
    """An answer, or a documented reason there is none."""

    available: bool
    provider: str
    model: str
    answer: str | None = None
    grounded: bool = Field(
        default=True,
        description=(
            "Whether every euro amount in the answer matches an amount this "
            "valuation produced. This is a numeric check and nothing more: it "
            "says the figures are ours, not that the answer's reasoning, "
            "comparisons or wording were verified. An answer can be grounded "
            "and still describe a relationship incorrectly. False means an "
            "amount appears that the valuation did not produce."
        ),
    )
    grounding_note: str | None = None
    unavailable_reason: str | None = None


class AiSuggestionsRead(ApiModel):
    """Example questions the current valuation can actually answer."""

    available: bool
    provider: str
    model: str
    questions: list[str] = Field(default_factory=list)
