"""SQLAlchemy models.

Importing this package registers every model on Base.metadata, which is what
Alembic autogeneration and the test fixtures rely on.
"""

from echte_auto_waarde.models.enums import (
    BodyType,
    DataSourceType,
    Drivetrain,
    FuelType,
    ImportMode,
    ImportRunStatus,
    ListingStatus,
    OptionCategory,
    SellerType,
    Transmission,
)
from echte_auto_waarde.models.import_run import ImportRun
from echte_auto_waarde.models.listing import (
    DataSource,
    Listing,
    ListingSnapshot,
    Seller,
)
from echte_auto_waarde.models.option import VehicleOption, VehicleOptionDefinition
from echte_auto_waarde.models.valuation import ComparableResultRecord, Valuation
from echte_auto_waarde.models.vehicle import Vehicle, VehicleSpecification

__all__ = [
    "BodyType",
    "ComparableResultRecord",
    "DataSource",
    "DataSourceType",
    "Drivetrain",
    "FuelType",
    "ImportMode",
    "ImportRun",
    "ImportRunStatus",
    "Listing",
    "ListingSnapshot",
    "ListingStatus",
    "OptionCategory",
    "Seller",
    "SellerType",
    "Transmission",
    "Valuation",
    "Vehicle",
    "VehicleOption",
    "VehicleOptionDefinition",
    "VehicleSpecification",
]
