from collections import Counter
from datetime import UTC, datetime

from echte_auto_waarde.data_sources.synthetic import (
    MODEL_VARIANTS,
    REFERENCE_DATE,
    SyntheticDataSource,
)
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

# Derived from the catalogue so adding a variant does not break the suite.
EXPECTED_LISTINGS = sum(variant.listing_count for variant in MODEL_VARIANTS)


def test_dataset_matches_the_declared_catalogue() -> None:
    listings = list(SyntheticDataSource().fetch_listings())
    assert len(listings) == EXPECTED_LISTINGS
    # Big enough to form comparable groups, small enough to stay a demo set.
    assert 100 <= len(listings) <= 200


def test_generation_is_deterministic_for_a_given_seed() -> None:
    first = list(SyntheticDataSource(seed=7, reference_date=REFERENCE_DATE).fetch_listings())
    second = list(SyntheticDataSource(seed=7, reference_date=REFERENCE_DATE).fetch_listings())
    assert first == second


def test_a_different_seed_produces_a_different_market() -> None:
    first = list(SyntheticDataSource(seed=7, reference_date=REFERENCE_DATE).fetch_listings())
    other = list(SyntheticDataSource(seed=8, reference_date=REFERENCE_DATE).fetch_listings())
    assert first != other


def test_source_is_labelled_synthetic_with_low_quality() -> None:
    source = SyntheticDataSource()
    assert source.source_type is DataSourceType.SYNTHETIC
    # Synthetic data validates methodology, not market accuracy, so it must not
    # be able to push the confidence model towards high confidence.
    assert source.quality < 0.5


def test_required_models_are_present_with_usable_group_sizes() -> None:
    listings = list(SyntheticDataSource().fetch_listings())
    counts = Counter((listing.vehicle.make, listing.vehicle.model.lower()) for listing in listings)

    makes = {make for make, _ in counts}
    assert {"BMW", "Volkswagen", "Mercedes-Benz", "Audi", "Tesla"} <= makes

    # Enough BMW 3 Series listings to form a meaningful comparable group.
    bmw_three_series = sum(
        count for (make, model), count in counts.items() if make == "BMW" and "3" in model
    )
    assert bmw_three_series >= 20


def test_listings_vary_across_the_dimensions_valuation_depends_on() -> None:
    listings = list(SyntheticDataSource().fetch_listings())

    assert len({listing.vehicle.year for listing in listings}) >= 5
    assert len({listing.vehicle.mileage_km for listing in listings}) >= 90
    assert len({listing.vehicle.trim for listing in listings}) >= 8
    assert len({listing.vehicle.fuel_type for listing in listings}) >= 4
    assert len({listing.vehicle.transmission for listing in listings}) >= 2
    assert len({listing.seller.seller_type for listing in listings if listing.seller}) == 2


def test_prices_are_plausible_and_advertised_in_round_steps() -> None:
    for listing in SyntheticDataSource().fetch_listings():
        assert 2_500_00 <= listing.asking_price_cents <= 100_000_00
        assert listing.asking_price_cents % 5_000 == 0


def test_history_supports_price_movement_analysis() -> None:
    listings = list(SyntheticDataSource().fetch_listings())
    reduced = [listing for listing in listings if listing.status is ListingStatus.PRICE_REDUCED]

    assert 10 <= len(reduced) <= 50
    for listing in reduced:
        first, last = listing.snapshots[0], listing.snapshots[-1]
        assert last.asking_price_cents < first.asking_price_cents
        assert last.observed_at > first.observed_at
        # The current asking price is the most recent observation.
        assert listing.asking_price_cents == last.asking_price_cents


def test_observations_stay_within_the_listing_lifetime() -> None:
    source = SyntheticDataSource(reference_date=REFERENCE_DATE)
    for listing in source.fetch_listings():
        assert listing.first_seen_at <= listing.last_seen_at == REFERENCE_DATE
        for snapshot in listing.snapshots:
            assert listing.first_seen_at <= snapshot.observed_at <= listing.last_seen_at


def test_option_texts_use_source_wording_that_needs_normalization() -> None:
    listings = list(SyntheticDataSource().fetch_listings())
    all_texts = {text for listing in listings for text in listing.vehicle.option_texts}
    # Raw wording, not canonical labels: ingestion has to normalize these.
    assert "adaptieve cruise control" in all_texts


def test_default_reference_date_keeps_the_market_recent() -> None:
    # A freshly seeded market must not look stale to the confidence model.
    listings = list(SyntheticDataSource().fetch_listings())
    today = datetime.now(UTC)
    for listing in listings:
        assert (today - listing.last_seen_at).days <= 1
        assert (today - listing.first_seen_at).days <= 121


def test_both_golf_generations_are_represented() -> None:
    # A market with only the newest generation cannot value an older car, which
    # is the situation this group was added to cover.
    generations = {
        listing.vehicle.generation
        for listing in SyntheticDataSource().fetch_listings()
        if listing.vehicle.model == "Golf"
    }
    assert {"Mk7", "Mk8"} <= generations
