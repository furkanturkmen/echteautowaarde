"""Vehicle schemas."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.schemas.common import ApiModel


class VehicleOptionRead(ApiModel):
    key: str
    label_nl: str
    category: str
    importance: float


class VehicleRead(ApiModel):
    id: int
    license_plate: str | None = None
    make: str
    model: str
    generation: str | None = None
    trim: str | None = None
    body_type: BodyType
    fuel_type: FuelType
    transmission: Transmission
    drivetrain: Drivetrain
    engine_description: str | None = None
    power_kw: int | None = None
    power_hp: int | None = None
    year: int | None = None
    first_registration_date: date | None = None
    mileage_km: int | None = None
    color: str | None = None
    doors: int | None = None
    seats: int | None = None
    catalog_price_cents: int | None = None
    options: list[VehicleOptionRead] = Field(default_factory=list)

    @classmethod
    def from_vehicle(cls, vehicle: Vehicle) -> VehicleRead:
        return cls(
            id=vehicle.id,
            license_plate=vehicle.license_plate,
            make=vehicle.make,
            model=vehicle.model,
            generation=vehicle.generation,
            trim=vehicle.trim,
            body_type=vehicle.body_type,
            fuel_type=vehicle.fuel_type,
            transmission=vehicle.transmission,
            drivetrain=vehicle.drivetrain,
            engine_description=vehicle.engine_description,
            power_kw=vehicle.power_kw,
            power_hp=vehicle.power_hp,
            year=vehicle.year,
            first_registration_date=vehicle.first_registration_date,
            mileage_km=vehicle.mileage_km,
            color=vehicle.color,
            doors=vehicle.doors,
            seats=vehicle.seats,
            catalog_price_cents=vehicle.catalog_price_cents,
            options=[
                VehicleOptionRead(
                    key=option.definition.key,
                    label_nl=option.definition.label_nl,
                    category=option.definition.category.value,
                    importance=option.definition.importance,
                )
                for option in vehicle.options
                if option.definition
            ],
        )


class ManualVehicleCreate(ApiModel):
    """A vehicle entered by hand, in whatever wording the user used.

    Everything is normalized on the way in; unrecognised values become UNKNOWN
    rather than a guess, which lowers confidence instead of corrupting matching.
    """

    make: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    year: int | None = Field(default=None, ge=1950, le=2100)
    mileage_km: int | None = Field(default=None, ge=0, le=2_000_000)
    trim: str | None = Field(default=None, max_length=64)
    generation: str | None = Field(default=None, max_length=32)
    body_type: str | None = Field(default=None, max_length=32)
    fuel_type: str | None = Field(default=None, max_length=32)
    transmission: str | None = Field(default=None, max_length=32)
    drivetrain: str | None = Field(default=None, max_length=32)
    engine_description: str | None = Field(default=None, max_length=64)
    power_hp: int | None = Field(default=None, ge=0, le=2_000)
    license_plate: str | None = Field(default=None, max_length=16)
    option_texts: list[str] = Field(default_factory=list, max_length=60)
