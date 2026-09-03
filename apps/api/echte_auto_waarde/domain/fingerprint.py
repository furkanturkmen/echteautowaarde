"""Vehicle fingerprint.

The normalized characteristics the comparable engine reasons about. Keeping this
as its own value object means the engine never touches ORM objects, database
sessions or raw source text — it compares normalized vehicles, and is trivially
testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass

from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission
from echte_auto_waarde.models.vehicle import Vehicle


@dataclass(frozen=True)
class VehicleFingerprint:
    make: str
    model: str
    generation: str | None = None
    body_type: BodyType = BodyType.UNKNOWN
    fuel_type: FuelType = FuelType.UNKNOWN
    transmission: Transmission = Transmission.UNKNOWN
    drivetrain: Drivetrain = Drivetrain.UNKNOWN
    engine_description: str | None = None
    power_hp: int | None = None
    year: int | None = None
    mileage_km: int | None = None
    trim: str | None = None
    option_keys: frozenset[str] = frozenset()

    @classmethod
    def from_vehicle(cls, vehicle: Vehicle) -> VehicleFingerprint:
        return cls(
            make=vehicle.make,
            model=vehicle.model,
            generation=vehicle.generation,
            body_type=vehicle.body_type,
            fuel_type=vehicle.fuel_type,
            transmission=vehicle.transmission,
            drivetrain=vehicle.drivetrain,
            engine_description=vehicle.engine_description,
            power_hp=vehicle.power_hp,
            year=vehicle.year,
            mileage_km=vehicle.mileage_km,
            trim=vehicle.trim,
            option_keys=frozenset(
                option.definition.key for option in vehicle.options if option.definition
            ),
        )

    @property
    def model_line(self) -> tuple[str, str]:
        return (self.make, self.model)

    def describe(self) -> str:
        """Short technical description, used in logs and AI context."""
        parts = [self.make, self.model]
        if self.engine_description:
            parts.append(self.engine_description)
        if self.trim:
            parts.append(self.trim)
        if self.year:
            parts.append(str(self.year))
        return " ".join(parts)

    # Fields that must be known for a valuation to be well supported. Missing
    # values do not block a valuation, but they lower confidence.
    REQUIRED_FOR_CONFIDENCE = ("generation", "year", "mileage_km", "fuel_type", "transmission")

    def missing_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        for field_name in self.REQUIRED_FOR_CONFIDENCE:
            value = getattr(self, field_name)
            if value is None or value in (
                BodyType.UNKNOWN,
                FuelType.UNKNOWN,
                Transmission.UNKNOWN,
                Drivetrain.UNKNOWN,
            ):
                missing.append(field_name)
        return tuple(missing)
