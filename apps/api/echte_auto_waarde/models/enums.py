"""Canonical enumerations shared by the persistence and domain layers.

Enum values are stored as plain strings in the database (never SQLite-specific
native enums) so the schema stays portable and readable in raw SQL.
"""

from __future__ import annotations

from enum import StrEnum


class BodyType(StrEnum):
    HATCHBACK = "HATCHBACK"
    SEDAN = "SEDAN"
    STATIONWAGON = "STATIONWAGON"
    SUV = "SUV"
    COUPE = "COUPE"
    CABRIOLET = "CABRIOLET"
    MPV = "MPV"
    UNKNOWN = "UNKNOWN"


class FuelType(StrEnum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    HYBRID = "HYBRID"
    PLUGIN_HYBRID = "PLUGIN_HYBRID"
    ELECTRIC = "ELECTRIC"
    LPG = "LPG"
    UNKNOWN = "UNKNOWN"


class Transmission(StrEnum):
    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"
    UNKNOWN = "UNKNOWN"


class Drivetrain(StrEnum):
    FWD = "FWD"
    RWD = "RWD"
    AWD = "AWD"
    UNKNOWN = "UNKNOWN"


class SellerType(StrEnum):
    PRIVATE = "PRIVATE"
    DEALER = "DEALER"
    UNKNOWN = "UNKNOWN"


class ListingStatus(StrEnum):
    """Lifecycle state of a listing.

    Observed facts live in listing snapshots; this field is the interpreted
    state. LIKELY_SOLD is only ever set by an explicit documented heuristic —
    a disappeared listing is REMOVED, not sold.
    """

    ACTIVE = "ACTIVE"
    PRICE_REDUCED = "PRICE_REDUCED"
    REMOVED = "REMOVED"
    LIKELY_SOLD = "LIKELY_SOLD"
    RELISTED = "RELISTED"
    UNKNOWN = "UNKNOWN"


class DataSourceType(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    CSV_IMPORT = "CSV_IMPORT"
    # Observations read from a dealer's own public inventory page.
    DEALER_SITE = "DEALER_SITE"
    RDW = "RDW"
    MANUAL = "MANUAL"


class ImportMode(StrEnum):
    """How an import file relates to the market it describes.

    The distinction exists for one reason: only a file that claims to be the
    complete picture of a scope can say anything about what is *absent* from it.
    """

    # A file of listings to add or refresh. Says nothing about what is missing.
    INCREMENTAL = "INCREMENTAL"
    # The complete set of listings for one source and scope at one moment. What
    # is absent from a successfully completed one is no longer being offered.
    FULL_SNAPSHOT = "FULL_SNAPSHOT"


class ImportRunStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OptionCategory(StrEnum):
    """Grouping used for display and for option-importance configuration."""

    TRIM_PACKAGE = "TRIM_PACKAGE"
    COMFORT = "COMFORT"
    SAFETY = "SAFETY"
    INFOTAINMENT = "INFOTAINMENT"
    EXTERIOR = "EXTERIOR"
    TOWING = "TOWING"
    OTHER = "OTHER"
