"""Deterministic synthetic market data.

This adapter fabricates a small Dutch-flavoured used-car market so the
comparable and valuation engines can be developed and tested offline. Nothing
here is real: no listing, seller, price or plate is copied from or intended to
match an actual vehicle or advertisement.

**The output is not real market data.** It exists to exercise the methodology,
not to produce accurate Dutch prices, and the UI labels it as synthetic.

The generator is seeded, so the same seed always produces the same market. Tests
depend on that. Observation timestamps are the one exception: they are offsets
from a reference date that defaults to the start of the current UTC day, so a
freshly seeded market never looks stale to the confidence model. Pass an
explicit `reference_date` when a test needs fixed timestamps.

Price construction (mirrors the shape of the valuation engine, so the engine has
something meaningful to recover):

    price = base_value * retention^age
          - (mileage - expected_mileage) * cents_per_km
          + option_value + trim_value
          + dealer_premium
          + noise (+/- 3.5%)

Expected mileage is 15.000 km per year, close to the Dutch average, so only the
*deviation* from normal use moves the price.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from echte_auto_waarde.data_sources.base import (
    RawListing,
    RawSeller,
    RawSnapshot,
    RawVehicle,
)
from echte_auto_waarde.domain.options import OPTIONS_BY_KEY, resolve_option
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

# Fixed reference date for tests that need stable timestamps.
REFERENCE_DATE = datetime(2026, 6, 1, tzinfo=UTC)


def current_reference_date() -> datetime:
    """Start of the current UTC day.

    Used as the default "today" of the synthetic market: listings observed
    within the last few months keep the freshness factor of the confidence model
    meaningful, while truncating to midnight keeps two generators created in the
    same session identical.
    """
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


DEFAULT_SEED = 20260601

EXPECTED_KM_PER_YEAR = 15_000
# Used-market effect of one kilometre of deviation from expected mileage.
CENTS_PER_KM = 6
# Used-market value of an option at importance 1.0, in EUR cents.
OPTION_VALUE_SCALE_CENTS = 90_000
# Used-market value of a full appearance package (M Sport, AMG Line, ...).
PACKAGE_TRIM_VALUE_CENTS = 110_000
# Dealers ask more than private sellers for otherwise identical cars.
DEALER_PREMIUM_RATIO = 0.04

DEALER_NAMES: tuple[str, ...] = (
    "Demo Autobedrijf Noord",
    "Demo Occasioncentrum Midden",
    "Demo Automotive Zuid",
    "Demo Car Company",
    "Demo Autopaleis",
    "Demo Auto Trading",
)

CITIES: tuple[str, ...] = (
    "Amsterdam",
    "Rotterdam",
    "Utrecht",
    "Eindhoven",
    "Groningen",
    "Zwolle",
    "Breda",
    "Arnhem",
    "Haarlem",
    "Tilburg",
)

COLORS: tuple[str, ...] = (
    "Zwart metallic",
    "Wit",
    "Grijs metallic",
    "Blauw metallic",
    "Zilver",
    "Donkergroen",
)


@dataclass(frozen=True)
class ModelVariant:
    """One recognisable market variant, e.g. a BMW 330e."""

    make: str
    model: str
    model_aliases: tuple[str, ...]
    generation: str
    engine_description: str
    fuel_type: str
    body_types: tuple[str, ...]
    transmissions: tuple[str, ...]
    drivetrain: str
    power_hp: int
    power_kw: int
    displacement_cc: int | None
    doors: int
    seats: int
    year_range: tuple[int, int]
    # Market value of a nearly-new example at expected mileage, in EUR cents.
    base_value_cents: int
    # Share of value retained per year of age.
    retention: float
    catalog_price_cents: int
    trims: tuple[str, ...]
    option_pool: tuple[str, ...]
    listing_count: int


# Option pools per segment. Aliases (not canonical labels) are used on purpose so
# the ingestion path exercises option normalization.
_PREMIUM_OPTIONS = (
    "panoramadak",
    "adaptieve cruise control",
    "leder",
    "stoelverwarming",
    "head-up display",
    "harman kardon",
    "matrix led",
    "achteruitrijcamera",
    "parkeersensoren",
    "elektrische stoelen",
    "trekhaak",
    "dodehoekdetectie",
    "adaptief onderstel",
    "19 inch velgen",
    "apple carplay",
)

_MAINSTREAM_OPTIONS = (
    "panoramadak",
    "adaptieve cruise control",
    "stoelverwarming",
    "achteruitrijcamera",
    "parkeersensoren",
    "navigatie",
    "apple carplay",
    "trekhaak",
    "climate control",
    "matrix led",
)

# An older mainstream car carries less driver assistance and lighting tech.
_OLDER_MAINSTREAM_OPTIONS = (
    "panoramadak",
    "stoelverwarming",
    "achteruitrijcamera",
    "parkeersensoren",
    "navigatie",
    "apple carplay",
    "trekhaak",
    "climate control",
)

_EV_OPTIONS = (
    "panoramadak",
    "leder",
    "stoelverwarming",
    "premium audio",
    "achteruitrijcamera",
    "19 inch velgen",
    "adaptieve cruise control",
)


MODEL_VARIANTS: tuple[ModelVariant, ...] = (
    ModelVariant(
        make="BMW",
        model="3 Serie",
        model_aliases=("3 Serie", "3-serie", "3 Series"),
        generation="G20",
        engine_description="330e",
        fuel_type="Plug-in hybride",
        body_types=("Sedan", "Touring"),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=292,
        power_kw=215,
        displacement_cc=1998,
        doors=4,
        seats=5,
        year_range=(2019, 2023),
        base_value_cents=5_200_000,
        retention=0.86,
        catalog_price_cents=6_150_000,
        trims=("M Sport", "M Sport", "Business Edition", "Executive"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=14,
    ),
    ModelVariant(
        make="BMW",
        model="3 Serie",
        model_aliases=("3 Serie", "3-serie"),
        generation="G20",
        engine_description="320i",
        fuel_type="Benzine",
        body_types=("Sedan", "Touring"),
        transmissions=("Automaat", "Handgeschakeld"),
        drivetrain="Achterwielaandrijving",
        power_hp=184,
        power_kw=135,
        displacement_cc=1998,
        doors=4,
        seats=5,
        year_range=(2019, 2023),
        base_value_cents=4_600_000,
        retention=0.85,
        catalog_price_cents=5_200_000,
        trims=("M Sport", "Business Edition", "Advantage"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="BMW",
        model="3 Serie",
        model_aliases=("3 Serie", "3 Series"),
        generation="G20",
        engine_description="320d",
        fuel_type="Diesel",
        body_types=("Sedan", "Touring"),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=190,
        power_kw=140,
        displacement_cc=1995,
        doors=4,
        seats=5,
        year_range=(2019, 2022),
        base_value_cents=4_500_000,
        retention=0.84,
        catalog_price_cents=5_400_000,
        trims=("M Sport", "Business Edition"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=4,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk8",
        engine_description="1.5 TSI",
        fuel_type="Benzine",
        body_types=("Hatchback",),
        transmissions=("Handgeschakeld", "Automaat"),
        drivetrain="Voorwielaandrijving",
        power_hp=150,
        power_kw=110,
        displacement_cc=1498,
        doors=5,
        seats=5,
        year_range=(2020, 2024),
        base_value_cents=3_300_000,
        retention=0.87,
        catalog_price_cents=3_700_000,
        trims=("R-Line", "Life", "Style"),
        option_pool=_MAINSTREAM_OPTIONS,
        listing_count=10,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk8",
        engine_description="2.0 TDI",
        fuel_type="Diesel",
        body_types=("Hatchback",),
        transmissions=("Automaat", "Handgeschakeld"),
        drivetrain="Voorwielaandrijving",
        power_hp=150,
        power_kw=110,
        displacement_cc=1968,
        doors=5,
        seats=5,
        year_range=(2020, 2023),
        base_value_cents=3_200_000,
        retention=0.86,
        catalog_price_cents=3_800_000,
        trims=("R-Line", "Life", "Style"),
        option_pool=_MAINSTREAM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk8",
        engine_description="GTE",
        fuel_type="Plug-in hybride",
        body_types=("Hatchback",),
        transmissions=("Automaat",),
        drivetrain="Voorwielaandrijving",
        power_hp=245,
        power_kw=180,
        displacement_cc=1395,
        doors=5,
        seats=5,
        year_range=(2020, 2023),
        base_value_cents=3_900_000,
        retention=0.85,
        catalog_price_cents=4_300_000,
        trims=("GTE", "R-Line"),
        option_pool=_MAINSTREAM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk7",
        engine_description="1.2 TSI",
        fuel_type="Benzine",
        body_types=("Hatchback", "Stationwagen"),
        transmissions=("Handgeschakeld", "Automaat"),
        drivetrain="Voorwielaandrijving",
        power_hp=105,
        power_kw=77,
        displacement_cc=1197,
        doors=5,
        seats=5,
        year_range=(2013, 2017),
        base_value_cents=3_100_000,
        # Older cars have already taken their steepest depreciation, so they
        # hold value more slowly from here.
        retention=0.885,
        catalog_price_cents=2_930_000,
        trims=("Comfortline", "Highline", "Trendline", "Cup Edition"),
        option_pool=_OLDER_MAINSTREAM_OPTIONS,
        listing_count=10,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk7",
        engine_description="1.4 TSI",
        fuel_type="Benzine",
        body_types=("Hatchback", "Stationwagen"),
        transmissions=("Automaat", "Handgeschakeld"),
        drivetrain="Voorwielaandrijving",
        power_hp=150,
        power_kw=110,
        displacement_cc=1395,
        doors=5,
        seats=5,
        year_range=(2013, 2017),
        base_value_cents=3_500_000,
        retention=0.88,
        catalog_price_cents=3_240_000,
        trims=("Highline", "R-Line", "Comfortline"),
        option_pool=_OLDER_MAINSTREAM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Volkswagen",
        model="Golf",
        model_aliases=("Golf",),
        generation="Mk7",
        engine_description="1.6 TDI",
        fuel_type="Diesel",
        body_types=("Stationwagen", "Hatchback"),
        transmissions=("Handgeschakeld", "Automaat"),
        drivetrain="Voorwielaandrijving",
        power_hp=110,
        power_kw=81,
        displacement_cc=1598,
        doors=5,
        seats=5,
        year_range=(2014, 2018),
        base_value_cents=3_300_000,
        retention=0.875,
        catalog_price_cents=3_150_000,
        trims=("Comfortline", "Highline", "Trendline"),
        option_pool=_OLDER_MAINSTREAM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Mercedes-Benz",
        model="C-Klasse",
        model_aliases=("C-Klasse", "C-Class"),
        generation="W206",
        engine_description="C200",
        fuel_type="Benzine",
        body_types=("Sedan", "Estate"),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=204,
        power_kw=150,
        displacement_cc=1496,
        doors=4,
        seats=5,
        year_range=(2021, 2024),
        base_value_cents=5_400_000,
        retention=0.86,
        catalog_price_cents=6_000_000,
        trims=("AMG Line", "Avantgarde", "Business Edition"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=7,
    ),
    ModelVariant(
        make="Mercedes-Benz",
        model="C-Klasse",
        model_aliases=("C-Klasse", "C Klasse"),
        generation="W205",
        engine_description="C220d",
        fuel_type="Diesel",
        body_types=("Sedan", "Estate"),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=200,
        power_kw=147,
        displacement_cc=1950,
        doors=4,
        seats=5,
        year_range=(2018, 2021),
        base_value_cents=4_300_000,
        retention=0.84,
        catalog_price_cents=5_500_000,
        trims=("AMG Line", "Avantgarde", "Business Solution"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Mercedes-Benz",
        model="C-Klasse",
        model_aliases=("C-Klasse",),
        generation="W206",
        engine_description="C300e",
        fuel_type="Plug-in hybride",
        body_types=("Sedan", "Estate"),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=320,
        power_kw=235,
        displacement_cc=1999,
        doors=4,
        seats=5,
        year_range=(2021, 2024),
        base_value_cents=6_200_000,
        retention=0.85,
        catalog_price_cents=7_100_000,
        trims=("AMG Line", "Avantgarde"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=5,
    ),
    ModelVariant(
        make="Audi",
        model="A4",
        model_aliases=("A4",),
        generation="B9",
        engine_description="35 TFSI",
        fuel_type="Benzine",
        body_types=("Sedan", "Avant"),
        transmissions=("Automaat", "Handgeschakeld"),
        drivetrain="Voorwielaandrijving",
        power_hp=150,
        power_kw=110,
        displacement_cc=1984,
        doors=4,
        seats=5,
        year_range=(2019, 2023),
        base_value_cents=4_400_000,
        retention=0.85,
        catalog_price_cents=5_000_000,
        trims=("S line", "Advanced", "Business Edition"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=7,
    ),
    ModelVariant(
        make="Audi",
        model="A4",
        model_aliases=("A4",),
        generation="B9",
        engine_description="40 TDI",
        fuel_type="Diesel",
        body_types=("Avant", "Sedan"),
        transmissions=("Automaat",),
        drivetrain="Voorwielaandrijving",
        power_hp=190,
        power_kw=140,
        displacement_cc=1968,
        doors=5,
        seats=5,
        year_range=(2019, 2023),
        base_value_cents=4_700_000,
        retention=0.85,
        catalog_price_cents=5_600_000,
        trims=("S line", "Advanced", "Business Edition"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Audi",
        model="A4",
        model_aliases=("A4",),
        generation="B9",
        engine_description="45 TFSI quattro",
        fuel_type="Benzine",
        body_types=("Avant", "Sedan"),
        transmissions=("Automaat",),
        drivetrain="Quattro",
        power_hp=265,
        power_kw=195,
        displacement_cc=1984,
        doors=5,
        seats=5,
        year_range=(2019, 2022),
        base_value_cents=5_300_000,
        retention=0.84,
        catalog_price_cents=6_400_000,
        trims=("S line", "Advanced"),
        option_pool=_PREMIUM_OPTIONS,
        listing_count=5,
    ),
    ModelVariant(
        make="Tesla",
        model="Model 3",
        model_aliases=("Model 3",),
        generation="Highland",
        engine_description="RWD",
        fuel_type="Elektrisch",
        body_types=("Sedan",),
        transmissions=("Automaat",),
        drivetrain="Achterwielaandrijving",
        power_hp=283,
        power_kw=208,
        displacement_cc=None,
        doors=4,
        seats=5,
        year_range=(2021, 2024),
        base_value_cents=4_300_000,
        retention=0.82,
        catalog_price_cents=4_600_000,
        trims=("Standard Range Plus",),
        option_pool=_EV_OPTIONS,
        listing_count=7,
    ),
    ModelVariant(
        make="Tesla",
        model="Model 3",
        model_aliases=("Model 3",),
        generation="Highland",
        engine_description="Long Range AWD",
        fuel_type="Elektrisch",
        body_types=("Sedan",),
        transmissions=("Automaat",),
        drivetrain="Dual Motor",
        power_hp=440,
        power_kw=324,
        displacement_cc=None,
        doors=4,
        seats=5,
        year_range=(2021, 2024),
        base_value_cents=5_100_000,
        retention=0.83,
        catalog_price_cents=5_500_000,
        trims=("Long Range",),
        option_pool=_EV_OPTIONS,
        listing_count=6,
    ),
    ModelVariant(
        make="Tesla",
        model="Model 3",
        model_aliases=("Model 3",),
        generation="Highland",
        engine_description="Performance",
        fuel_type="Elektrisch",
        body_types=("Sedan",),
        transmissions=("Automaat",),
        drivetrain="Dual Motor",
        power_hp=487,
        power_kw=357,
        displacement_cc=None,
        doors=4,
        seats=5,
        year_range=(2021, 2024),
        base_value_cents=5_700_000,
        retention=0.82,
        catalog_price_cents=6_300_000,
        trims=("Performance",),
        option_pool=_EV_OPTIONS,
        listing_count=5,
    ),
)

PACKAGE_TRIMS = frozenset({"M Sport", "AMG Line", "S line", "R-Line", "GTE"})


def _plate_for(index: int) -> str:
    """Deterministic demo plate.

    Formatted like a Dutch plate so the interface can be developed realistically.
    These plates identify nothing: the vehicles are fictional, no owner data is
    stored, and lookups only ever search this local synthetic dataset.
    """
    letters = "BDFGHJKLNPRSTVXZ"
    first = letters[index % len(letters)]
    second = letters[(index // len(letters)) % len(letters)]
    return f"{first}{second}-{100 + (index * 7) % 900}-{letters[(index * 3) % len(letters)]}"


def _option_value_cents(option_keys: Sequence[str]) -> int:
    total = 0.0
    for key in option_keys:
        definition = OPTIONS_BY_KEY.get(key)
        if definition is not None:
            total += definition.importance * OPTION_VALUE_SCALE_CENTS
    return int(total)


class SyntheticDataSource:
    """Deterministic fictional market data. Implements `DataSourceAdapter`."""

    key = "synthetic"
    source_type = DataSourceType.SYNTHETIC
    name = "Synthetische demomarkt"
    # Deliberately low: this data validates methodology, never market accuracy.
    quality = 0.35

    def __init__(
        self,
        seed: int = DEFAULT_SEED,
        reference_date: datetime | None = None,
        variants: Sequence[ModelVariant] = MODEL_VARIANTS,
    ) -> None:
        self._seed = seed
        self._reference_date = reference_date or current_reference_date()
        self._variants = tuple(variants)

    def fetch_listings(self) -> Iterable[RawListing]:
        rng = random.Random(self._seed)
        index = 0
        for variant in self._variants:
            for _ in range(variant.listing_count):
                yield self._build_listing(rng, variant, index)
                index += 1

    def _build_listing(self, rng: random.Random, variant: ModelVariant, index: int) -> RawListing:
        year = rng.randint(*variant.year_range)
        age_years = max(self._reference_date.year - year, 0)

        expected_km = max(age_years, 1) * EXPECTED_KM_PER_YEAR
        mileage_km = max(int(expected_km * rng.uniform(0.55, 1.55)), 4_000)

        trim = rng.choice(variant.trims)
        option_count = rng.randint(2, min(7, len(variant.option_pool)))
        option_texts = tuple(rng.sample(list(variant.option_pool), option_count))
        option_keys = [
            definition.key
            for definition in (resolve_option(text) for text in option_texts)
            if definition is not None
        ]

        seller_is_dealer = rng.random() < 0.72
        base = variant.base_value_cents * (variant.retention**age_years)
        price = base
        price -= (mileage_km - expected_km) * CENTS_PER_KM
        price += _option_value_cents(option_keys)
        if trim in PACKAGE_TRIMS:
            price += PACKAGE_TRIM_VALUE_CENTS
        if seller_is_dealer:
            price *= 1 + DEALER_PREMIUM_RATIO
        price *= rng.uniform(0.965, 1.035)

        # Dutch asking prices are advertised in round steps of 50 euro.
        asking_price_cents = max(int(round(price / 5_000) * 5_000), 250_000)

        first_seen_at = self._reference_date - timedelta(days=rng.randint(3, 120))
        snapshots, status, asking_price_cents = self._build_history(
            rng, first_seen_at, asking_price_cents, mileage_km
        )

        raw_vehicle = RawVehicle(
            make=variant.make,
            model=rng.choice(variant.model_aliases),
            year=year,
            mileage_km=mileage_km,
            trim=trim,
            generation=variant.generation,
            body_type=rng.choice(variant.body_types),
            fuel_type=variant.fuel_type,
            transmission=rng.choice(variant.transmissions),
            drivetrain=variant.drivetrain,
            engine_description=variant.engine_description,
            engine_displacement_cc=variant.displacement_cc,
            power_kw=variant.power_kw,
            power_hp=variant.power_hp,
            first_registration_date=date(year, rng.randint(1, 12), rng.randint(1, 28)),
            license_plate=_plate_for(index),
            color=rng.choice(COLORS),
            doors=variant.doors,
            seats=variant.seats,
            catalog_price_cents=variant.catalog_price_cents,
            option_texts=option_texts,
        )

        seller = (
            RawSeller(
                seller_type="DEALER",
                name=rng.choice(DEALER_NAMES),
                city=rng.choice(CITIES),
            )
            if seller_is_dealer
            else RawSeller(seller_type="PRIVATE", name=None, city=rng.choice(CITIES))
        )

        return RawListing(
            external_reference=f"SYN-{index:04d}",
            vehicle=raw_vehicle,
            asking_price_cents=asking_price_cents,
            first_seen_at=first_seen_at,
            last_seen_at=self._reference_date,
            seller=seller,
            url=None,
            status=status,
            snapshots=snapshots,
        )

    def _build_history(
        self,
        rng: random.Random,
        first_seen_at: datetime,
        asking_price_cents: int,
        mileage_km: int,
    ) -> tuple[tuple[RawSnapshot, ...], ListingStatus, int]:
        """Build the observation history, sometimes including a price reduction.

        Roughly a third of listings are reduced after a while, which is what
        makes days-on-market and price-movement analytics meaningful later. The
        reduced price becomes the current asking price.
        """
        days_listed = (self._reference_date - first_seen_at).days
        reduced = rng.random() < 0.32 and days_listed > 21

        if not reduced:
            return (
                (
                    RawSnapshot(
                        observed_at=first_seen_at,
                        asking_price_cents=asking_price_cents,
                        mileage_km=mileage_km,
                        status=ListingStatus.ACTIVE,
                    ),
                ),
                ListingStatus.ACTIVE,
                asking_price_cents,
            )

        original_price = int(round(asking_price_cents * rng.uniform(1.02, 1.06) / 5_000) * 5_000)
        reduction_at = first_seen_at + timedelta(days=rng.randint(14, max(15, days_listed - 1)))
        return (
            (
                RawSnapshot(
                    observed_at=first_seen_at,
                    asking_price_cents=original_price,
                    mileage_km=mileage_km,
                    status=ListingStatus.ACTIVE,
                ),
                RawSnapshot(
                    observed_at=reduction_at,
                    asking_price_cents=asking_price_cents,
                    mileage_km=mileage_km,
                    status=ListingStatus.PRICE_REDUCED,
                ),
            ),
            ListingStatus.PRICE_REDUCED,
            asking_price_cents,
        )
